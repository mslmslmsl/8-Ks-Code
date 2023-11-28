"""Script to pull Form 8-K filings from the SEC site and index on GitHub."""

import os
import re
from datetime import datetime
import logging
import base64

from bs4 import BeautifulSoup
import requests

# Constants
TESTING = False
ITEM = "5.02" if TESTING else "1.05"
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    raise ValueError("GitHub token not found. Set the GITHUB_TOKEN env var.")
REPO_OWNER = "mslmslmsl"
REPO_NAME = "TEST" if TESTING else "8-Ks"
FILE_PATH = "8-Ks.md"
GITHUB_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/"
    f"{REPO_NAME}/contents/{FILE_PATH}"
)
HEADING = (
    f"# List of Form 8-Ks with item {ITEM}\n"
    f"Last checked {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    "|Company|Timestamp|Link|\n"
    "|---|---|---|\n"
)
GITHUB_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3.raw",
}
FILINGS_PER_PAGE = 100  # This should only be from [10, 20, 40, 80, or 100]
SEC_TIMEOUT = 10
SEC_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    )
}

# Show me the logs
logging.basicConfig(level=logging.INFO)


def get_sec_url(index: int) -> str:
    """Return the URL for the relevant page of the 'latest filings' site"""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&datea=&dateb=&company=&type=8-k&SIC=&State=&Country=&CIK=&owner="
        f"include&accno=&start={index}&count={FILINGS_PER_PAGE}"
    )


def update_github_file(entries_to_file: str, current_sha: str) -> None:
    """Update the GitHub file with the latest Form 8-K entries."""

    # Set the content of the file to HEADING plus the entries
    full_content = HEADING
    full_content += entries_to_file if entries_to_file else ''

    # Upload to GitHub
    message = f"Update {FILE_PATH}" if current_sha else f"Create {FILE_PATH}"
    payload = {
        "message": message,
        "content": base64.b64encode(full_content.encode()).decode('utf-8'),
        "sha": current_sha.strip('"') if current_sha else None
    }
    response = requests.put(
        GITHUB_API_URL, headers=GITHUB_HEADERS, json=payload, timeout=10
    )

    # Log the response
    if response.status_code == 200:
        logging.info("Updated %s successfully.\n", FILE_PATH)
    elif response.status_code == 201:
        logging.info("Created %s successfully.\n", FILE_PATH)
    else:
        logging.error(
            "Error interacting with %s. HTTP Status Code: %s, Response: %s\n",
            FILE_PATH,
            response.status_code,
            response.text
        )


def get_filing_info(element: tuple) -> str:
    """Extract information from Form 8-K filing HTML element."""
    soup = BeautifulSoup(str(element[0]), 'html.parser')

    # Get the company name (assume that an <a> tag always exists in element[0])
    company = soup.find('a').get_text()
    company = re.sub(r'\([^)]*\) \(Filer\)\s*', '', company).strip()

    soup = BeautifulSoup(str(element[1]), 'html.parser')

    # Get the timestamp (and assume that a <td> tag with a <br> tag always
    # exists in element[1])
    date_time = (
        soup.find(
            lambda tag: tag.name == 'td' and tag.find('br'),
            {'nowrap': 'nowrap'}
        )
        .get_text()
    )
    date_time_obj = datetime.strptime(date_time, '%Y-%m-%d%H:%M:%S')
    date_time = date_time_obj.strftime("%Y-%m-%d %H:%M:%S")

    # Get the URL to the actual form filing
    html_link = soup.find('a', string='[html]')
    full_url = f"[link](https://www.sec.gov{html_link.get('href')})"

    # Return a string with the data
    return f"|{company}|{date_time}|{full_url}|\n"


def get_newest_timestamp(text: str):
    """Return the timestamp fo the first filing on the page"""

    pattern = re.compile(r'\d{4}-\d{2}-\d{2}\d{2}:\d{2}:\d{2}')
    ugly_newest_on_page_string = pattern.findall(text)[0]
    newest_on_page_obj = datetime.strptime(
        ugly_newest_on_page_string,
        "%Y-%m-%d%H:%M:%S"
    )
    newest_on_page_string = newest_on_page_obj.strftime("%Y-%m-%d %H:%M:%S")
    return newest_on_page_string


def get_8ks(last_checked_datetime_string: str) -> str:
    """Retrieve Form 8-K filings from the SEC's 'latest filings' page."""
    index = 0
    relevant_filings = ''

    # Loop through each page of the SEC 'latest filings' site
    while True:

        # Request the page
        try:
            logging.info(
                "Extracting data from page %s.",
                int((index+FILINGS_PER_PAGE)/FILINGS_PER_PAGE)
            )
            page_url = get_sec_url(index)
            with requests.Session() as session:
                response = session.get(
                    page_url,
                    headers=SEC_HEADERS,
                    timeout=SEC_TIMEOUT
                )

            # If the page doesn't load, throw an error and return
            if response.status_code != 200:
                logging.error(
                    "Failed to load SEC data (code: %s) for URL: %s.",
                    response.status_code,
                    page_url
                )
                return None

            soup = BeautifulSoup(response.text, 'html.parser')

            # Find all <tr> elements, each of which is a filing
            tr_elements = soup.find_all('tr')

            newest_filing_on_page = ''
            tr_elements_with_item = []

            # Loop through all the rows on the page
            for prev_tr, current_tr in zip(tr_elements, tr_elements[1:]):
                text = current_tr.get_text()

                # Do stuff if we find a filing row (has "Current report")
                if "Current report" in text:
                    # Save the timestamp for the first filing on the pae
                    if not newest_filing_on_page:
                        newest_filing_on_page = get_newest_timestamp(text)
                    # If the filing has our item, save it for processing
                    if ITEM in text:
                        tr_elements_with_item.append((prev_tr, current_tr))

            # For each filin wiht our item, extract co name, timestamp, link
            for tr_element in tr_elements_with_item:
                relevant_filings += get_filing_info(tr_element)

            # Break loop if we have already reviewed the page
            if last_checked_datetime_string >= newest_filing_on_page:
                logging.info("Done extracting new data from the SEC pages.")
                break

            # Break loop if on the last page (no 'next page' button)
            if not soup.find('input', {'value': f'Next {FILINGS_PER_PAGE}'}):
                logging.info(
                    "We are on the last page, so no more filings to analyze."
                )
                break

            # Update index to get the next page of 8-Ks
            index += FILINGS_PER_PAGE

        except requests.Timeout:
            # Log a warning if the request times out
            logging.warning(
                "Request to %s timed out after %s seconds.",
                page_url,
                SEC_TIMEOUT
            )

        except requests.RequestException as e:
            # Log other request exceptions if needed
            logging.warning(
                "Request to %s encountered an exception: %s.", page_url, e
            )

    return relevant_filings


def get_exisiting_data() -> tuple:
    """Retrieve existing Form 8-K entries from the GitHub repo."""

    # Pull data from GitHub
    try:
        response = requests.get(
            GITHUB_API_URL, headers=GITHUB_HEADERS, timeout=10
        )

        # If we succeed, then process the existing entries
        if response.status_code == 200:

            # Get the sha of the response (which has to be sent back)
            current_sha = response.headers.get('ETag')

            # Get lines from the file and create a list of strings
            current_content = response.text.replace('\r', '')
            current_content_as_strings = current_content.splitlines()

            # Isolate the form 8-K lines
            bottom_half = current_content_as_strings[HEADING.count('\n'):]

            # Get the datetime of the last check -- this is to avoid
            # analyzing SEC pages that we've already reviewed
            if current_content_as_strings:
                last_checked = re.search(
                    r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
                    current_content_as_strings[1]
                ).group()
            else:
                last_checked = '1970-01-01 00:00:00'

            return bottom_half, current_sha, last_checked

        logging.info("%s doesn't exist, so creating it.", FILE_PATH)
        return None, None, '1970-01-01 00:00:00'

    except requests.exceptions.RequestException as exception:
        logging.error(
            "An error occurred during the request: %s", str(exception)
        )
        return None, None, '1970-01-01 00:00:00'


def get_final_string(new_entries: list, old_entries: list) -> str:
    """Create the final str of filings; combine new and old lists if needed"""

    # Define variable to store the final list of filings
    final_list = []

    # If there are existing filings, combine new and old lists
    if old_entries:
        cutoff_timestamp = old_entries[0].split('|')[2]
        for entry in new_entries:
            # Only add new entries that are more recent than the newest old one
            if entry.split('|')[2] > cutoff_timestamp:
                final_list.append(entry)
            else:
                break
        final_list += old_entries
    # If there are no existing filings, then the full list is just the new list
    else:
        final_list += new_entries

    return '\n'.join(final_list)


def main():
    """Main function to check and update the Form 8-K entries on GitHub."""

    # Get existing filings as a list of strings (one filing per string)
    # If there are existing entries, get the sha (needed to update a file)
    logging.info(
        "Retrieving existing data from %s/%s.",
        REPO_NAME,
        FILE_PATH
    )
    existing_entries_list, current_sha, latest_checked_datetime_string = \
        get_exisiting_data()

    # Get new filings as a string
    logging.info("Attempting to access the SEC 'latest filings' page.")
    new_entries_string = get_8ks(latest_checked_datetime_string)

    # Turn the new entries into a list of strings (one filing per string)
    new_entries_list = new_entries_string.splitlines()

    # Get the final string to be saved
    logging.info("Creating final list of filings to save.")
    all_entries_string = get_final_string(
        new_entries_list,
        existing_entries_list
    )

    # Save the filings to GitHub (by either creating or updating the file)
    logging.info("Saving new filings to %s.", FILE_PATH)
    update_github_file(all_entries_string, current_sha)


if __name__ == "__main__":
    main()
