# SEC Form 8-K Indexer

## Description

The SEC Form 8-K Indexer is a Python script that finds and analyzes Form 8-Ks filed with the U.S. Securities and Exchange Commission (SEC) (and so available on the SEC's ["Latest Filings Received and Processed at the SEC" page](https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent)). It logs any 8-Ks filed that contain the specified "item" provided and updates a GitHub repo with information about the 8-Ks.

In addition, it uses OpenAI's API to analyze the content of the logged 8-Ks and determine whether the filing companies consider the reported events to be material. The OpenAI prompt can be found in `instructions.txt`. By default, the script focuses on item 1.05 (material cybersecurity incidents). If you intend to analyze other items, please update the prompt accordingly.

An example of the output is available [here](https://github.com/8-K-bot/8-Ks/blob/main/8-Ks.md).

## Usage Instructions

The "Latest Filings" page on the SEC website displays forms filed with the SEC in the **past three business days**. To ensure that the script reviews all filings, you need to run the script at least **twice a week**. For example:

- Between **Wednesday at 10 PM ET and Thursday at 6 AM ET** to scan filings submitted on Monday, Tuesday, or Wednesday.
- Between **Friday at 10 PM ET and Tuesday at 6 AM ET** to scan filings submitted on Thursday or Friday.

To automate the scanning of the 'Latest Filings' page, configure a cron job to run the script. For example:

- `0 8-22/2 * * 1-5 python ~/path/to/your/form_8k_checker.py` to run the script every other hour between 8 AM and 10 PM from Monday to Friday.
- `0 22 * * 3,5 python ~/path/to/your/form_8k_checker.py` to run the script at 10 PM on Wednesday and Friday.

## Prerequisites and Configuration

Before running the script, ensure you have Python 3.x and the necessary dependencies (install with `pip install -r requirements.txt`).

Also, update the following constants and global variables in the script:

- `TESTING`: Set to True to test the script with a more common item and a private repo.
- `ITEM`: Identify the 8-Ks to index by specifying the item that the script looks for in the 8-Ks (the default is 1.05 - Material Cybersecurity Incidents).
- `GITHUB_TOKEN`, `REPO_OWNER`, and `REPO_NAME`: Configure your GitHub repo information and include a GitHub token.
- `FILE_PATH`: Specify the filename within the repo where the Form 8-K list will be stored.
- `DETERMINE_MATERIALITY`: Set to True to use OpenAI to determine if a filing company thinks that the incident it experienced was material.
- `OPENAI_API_KEY`: Specify your OpenAI API key if you enable the feature to determine whether an incident was material.
