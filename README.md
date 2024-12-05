# ICVul Dataset Project

This project is designed to extract, analyze, and filter CVEs (Common Vulnerabilities and Exposures) from the National Vulnerability Database (NVD) and then associate them with fix commits from GitHub open-source repositories. By using the SZZ algorithm, it identifies Vulnerable Commit Changes (VCCs) and extracts relevant commit information.

## Table of Contents
1. [Project Overview](#project-overview)
2. [Prerequisites](#prerequisites)
3. [Workflow](#workflow)
4. [Key Modules](#key-modules)
5. [Logging](#logging)
6. [Notes](#notes)
7. [Citation](#citation)

## Project Overview

This project processes and analyzes data from CVE, CWE, and related repositories to generate mappings between vulnerabilities and their associated commits, repositories, and files. The pipeline involves several steps: extracting repository information, processing and filtering commit data, and removing noise to focus on relevant information.

## Prerequisites

### 1. Python Environment
Ensure you have Python installed along with the following packages:
- `pandas`, `pydriller`,`github`,`git`

### 2. GitHub Token
Set up a valid GitHub token to enable the script to fetch repository information. Replace the placeholder in the script:
- github_token = 'your_github_token'


This project automates the extraction of CVEs from the NVD and identifies fix commits that resolve those vulnerabilities in open-source software repositories. It uses the SZZ algorithm to trace VCCs (Vulnerable Commit Changes), which is vital for vulnerability remediation and analysis.

## Workflow

#### Step 1: Extract Repository Information
#### Step 2: Process Commit/file/function Data and cve_fc_vcc_mapping table
#### Step 3: Eliminate Suspicious Commits (ESC)

- **Execution**:  
  Update `step = 1` (3 steps in order )in `main.py` and run the following command:
  ```bash
  python main.py

## Key Modules
- `data_structure`
Defines the structure of the five tables.

- `vcc_extraction`
Handles the fetching of VCC URLs for commits (including SZZ algorithm).

- `commit_extraction`
Handles the fetching of files and functions.

- `repo_extraction`
Provides methods to extract repository metadata and validate repository URLs.

- `fc_filter_ESC`
Implements filtering logic to eliminate suspicious or noisy commits.

- `utils`
Provides utility functions, including parallel processing of URLs.


## Logging
All steps log progress and results to log/running.log

## Notes
- Token Management: Ensure your GitHub token has sufficient permissions to access the repositories in question.
- Custom Adjustments: If you encounter commits requiring manual correction (e.g., fc_hash adjustments), edit the script as indicated in the comments.

## Citation
If you use this repository or its outputs in your research, please cite the associated paper: