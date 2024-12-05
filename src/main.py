# main.py
import pandas as pd
from data_structure import repo_columns, cve_cwe_commit_columns
from vcc_extraction import get_vcc_url
from repo_extraction import extract_repo_name_url, fetch_repo_info
from fc_filter_ESC import map_commit_info, delete_outliers_by_msg, delete_outliers_by_vcc
from utils import process_multiple_urls
import logging

# Set up the root logger
logging.basicConfig(filename='..//log/running.log', level=logging.INFO,
                    format='%(asctime)s %(name)s %(levelname)s %(message)s',
                    datefmt='%m/%d/%Y %H:%M:%S')

# Adjust the logging level for specific libraries or modules
logging.getLogger('pydriller').setLevel(logging.WARNING)

if __name__ == "__main__":
    parallel_max_workers = 20
    github_token = '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'
    step = 3

    if step == 1:
        """
        # Step1: Store info to Table: repository_info.
        """
        df = pd.read_csv('..//data/raw/filtered_cves.csv')
        df['repo_url'], df['repo_name'] = zip(*df['Reference URLs'].apply(extract_repo_name_url))
        # Create a new DataFrame to store unique repository URLs
        unique_repos_df = df.drop_duplicates(subset='repo_name')
        # Fetch metadata for each unique repository URL in parallel
        metadata_list, unreachable_url = fetch_repo_info(unique_repos_df['repo_url'], github_token,
                                                         parallel_max_workers)
        # Create a DataFrame from the list of metadata dictionaries
        repo_info_df = pd.DataFrame(metadata_list, columns=repo_columns)
        repo_info_df['repo_url'] = repo_info_df['repo_url'].str.replace(r'^http:', 'https:', regex=True)
        repo_info_df = repo_info_df[(repo_info_df['repo_language'] == 'C') | (repo_info_df['repo_language'] == 'C++')]
        repo_info_df.to_csv('..//data/processed/repository_info.csv', index=False)
        logging.info(f"------------------------------------------------------------------------------")
        logging.info(f"Unique repository in total: {unique_repos_df.shape[0]}")
        logging.info(f"Unreachable repository url in total: {len(unreachable_url)}")
        logging.info(f"Successfully store info to Table0: repository_info, table shape: {repo_info_df.shape}")
        logging.info(f"------------------------------------------------------------------------------")

    if step == 2:
        """
        # Step2: Store all other info.
        """
        df = pd.read_csv('..//data/processed/final_cves.csv')
        df[['repo_url', 'fc_hash']] = df['Reference URLs'].apply(process_multiple_urls)
        # Group by repo_url and aggregate fc_hash into a list of hashes
        repo_url_hash_df = df.groupby('repo_url')['fc_hash'].apply(
            lambda x: [hash_item for sublist in x for hash_item in sublist]).reset_index()

        df1 = pd.read_csv('../data/processed/repository_info.csv')
        value_repo_df = df1['repo_url'].tolist()
        repo_url_hash_df = repo_url_hash_df[repo_url_hash_df['repo_url'].isin(value_repo_df)]
        repo_url_hash_df['list_length'] = repo_url_hash_df['fc_hash'].apply(len)  # count the length of each row
        repo_url_hash_df = repo_url_hash_df.sort_values(by='list_length', ascending=False).drop(
            columns=['list_length']).reset_index(drop=True)
        get_vcc_url(repo_url_hash_df, parallel_max_workers)
        print("Done!")
        # Build and store the cve_fc_vcc_mapping table
        new_df = df[df['repo_url'].isin(value_repo_df)]
        new_df = new_df.drop(columns=['Description', 'Reference URLs', 'Patch URL'])
        new_df = new_df.rename(columns={'CVE ID': 'cve_id', 'CWE ID': 'cwe_id'})
        new_df = new_df.explode('fc_hash')  # break to multi_row
        df2 = pd.read_csv('..//data/processed/fc_vcc_hash.csv')
        result_df = pd.merge(new_df, df2, on='fc_hash', how='left')
        result_df.to_csv('..//data/processed/cve_fc_vcc_mapping.csv', index=False)
    # change this manually
    # if fc_hash == "curl-7_51_0-162-g3ab3c16":
    #     fc_hash = "3ab3c16db6a5674f53cf23d56512a405fde0b2c9"
    # if fc_hash == "curl-7_50_2~32":
    #     fc_hash = "7700fcba64bf5806de28f6c1c7da3b4f0b38567d"

    if step == 3:
        """
        # Step3: ESC (Eliminate Suspicious Commit), delete all noise data
        """
        df1 = pd.read_csv('..//data/processed/cve_fc_vcc_mapping.csv')
        df2 = pd.read_csv('..//data/processed/commit_info.csv')
        df = map_commit_info(df1, df2)
        msg_outliers_df = df[df['msg'].apply(delete_outliers_by_msg)]
        msg_outliers_list = msg_outliers_df['hash'].tolist()

        log_file_path = '..//log/running.log'
        outliers_by_vcc_list = delete_outliers_by_vcc(log_file_path)

        # If the FC belongs to more than one CWE type
        duplicates = df1.groupby('fc_hash')['cwe_id'].nunique()
        outliers_different_cwe_list = list(duplicates[duplicates > 1].index)

        # delete_outliers_by_count
        function_df = pd.read_csv('..//data/processed/function_info.csv')
        vulnerable_functions = function_df['hash'].value_counts()
        outliers_over_100funcs_list = vulnerable_functions[vulnerable_functions > 100].index.tolist()

        # merge outliers
        all_outliers_list = list(set(msg_outliers_list + outliers_by_vcc_list
                                     + outliers_different_cwe_list + outliers_over_100funcs_list))

        """
        # Delete related outliers data in all tables
        # mapping, commit, file, commit
        """
        deleted_rows = df1[df1['fc_hash'].isin(all_outliers_list)]
        outliers_related_vcc_list = [item for sublist in deleted_rows['vcc_hash'].dropna().tolist() for item in sublist]
        mapping_filtered = df1[~df1['fc_hash'].isin(all_outliers_list)]
        mapping_filtered.to_csv('..//data/processed/cve_fc_vcc_mapping.csv', index=False)

        all_outliers_list = list(set(outliers_related_vcc_list + all_outliers_list))
        commit_filtered = df2[~df2['hash'].isin(all_outliers_list)]
        commit_filtered.to_csv('..//data/processed/commit_info.csv', index=False)

        df3 = pd.read_csv('..//data/processed/file_info.csv')
        file_filtered = df3[~df3['hash'].isin(all_outliers_list)]
        file_filtered.to_csv('..//data/processed/file_info.csv', index=False)

        df4 = pd.read_csv('..//data/processed/function_info.csv')
        function_filtered = df4[~df4['hash'].isin(all_outliers_list)]
        function_filtered.to_csv('..//data/processed/function_info.csv', index=False)






