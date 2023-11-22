# SEC Form 8-K Indexer

This is a Python script designed to automate the extraction of Form 8-K filings from the U.S. Securities and Exchange Commission (SEC) ["Latest Filings Received and Processed at the SEC" page](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent). The script only collects the 8-K filings that include a specific item, and it updates a list on GitHub with the relevant information.

## Prerequisites

Before using the script, ensure you have the necessary dependencies installed:

    Python 3.x
    Required Python packages (install via pip install -r requirements.txt)

## Usage

1. Clone the repository:

        git clone https://github.com/mslmslmsl/8-Ks.git
        cd 8-Ks

2. Set up your GitHub token:

        export GITHUB_TOKEN="your_github_token_here"

3. Run the script:

        python form_8k_checker.py

## Configuration

Before running the script, you'll need to configure the following settings:

- **TESTING:**
  - This option is used for testing the script with a more common item and a private repository.

- **ITEM:**
  - Specify the relevant item to filter Form 8-K filings. This ensures that the script extracts filings containing the specified item.

- **GITHUB_TOKEN:**
  - Since the script saves the output to a file in a GitHub repo, you'll need to configure the repo information (see below) and include a GitHub token.

- **REPO_OWNER:**
  - Set the repo owner that owns the repo where the Form 8-K list will be stored.

- **REPO_NAME:**
  - Set the name of the repo where the Form 8-K list will be stored.

- **FILE_PATH:**
  - Specify the file path within the repo where the Form 8-K list will be stored.

If you plan to keep the script and output file in the same repo, please review the next section re: fetching changes to avoid conflicts when updating or running the script.

## Important: Regularly Fetch Changes

If you plan to keep the script and the output file in the same repo, then in order to prevent conflicts, make sure to always check for updates and regularly fetch changes from the remote repo (e.g., by using `git pull`). Failure to do so may result in conflicts if the script updates the output file in your remote repo.
