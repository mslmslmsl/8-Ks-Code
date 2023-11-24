# SEC Form 8-K Indexer

## Description

The SEC Form 8-K Indexer is a Python script that automates the extraction of Form 8-K filings from the U.S. Securities and Exchange Commission (SEC) ["Latest Filings Received and Processed at the SEC" page](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent). It collects 8-K filings that include the specified "item" provided and updates a GitHub repo with information about the filings (including a link to the filings themselves).

## Usage Instructions

The "Latest Filings" page on the SEC website displays forms filed with the SEC in the **past three business days**. To ensure that the script reviews all filings, it's recommended to run the script at least **twice a week**. For example:

- Between **Wednesday at 6 PM ET and Thursday at 6 AM ET** to scan filings submitted on Monday, Tuesday, or Wednesday.
- Between **Friday at 6 PM ET and Tuesday at 6 AM ET** to scan filings submitted on Thursday or Friday.

## Prerequisites and Configuration

Before running the script, ensure you have Python 3.x and the necessary dependencies (install with `pip install -r requirements.txt`).

Also, update the following constants in the script:

- `TESTING`: Used for testing the script with a more common Form 8-K item and a private repo.
- `ITEM`: Identify the 8-Ks to index by specifying the item (default is 1.05 - Material Cybersecurity Incidents).
- `GITHUB_TOKEN`, `REPO_OWNER`, and `REPO_NAME`: Configure your GitHub repo information and include a GitHub token.
- `FILE_PATH`: Specify the filename within the repo where the Form 8-K list will be stored.

## Regularly Fetch Changes

If you decide to keep the script and the output file in the same repository, make sure to regularly check for updates using `git pull` to prevent conflicts. However, it's probably better to keep the script local and update only the output file in the repo to avoid potential conflicts.
