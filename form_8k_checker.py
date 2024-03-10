"""Script to pull Form 8-K filings from the SEC site and index on GitHub."""

import os
import re
from datetime import datetime
import logging
import base64

from bs4 import BeautifulSoup
import requests
from openai import OpenAI
import tiktoken

# Constants and global variables
TESTING = True
DETERMINE_MATERIALITY = True
ITEM = "1.01" if TESTING else "1.05"
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if OPENAI_API_KEY is None:
    DETERMINE_MATERIALITY = False
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
if GITHUB_TOKEN is None:
    raise ValueError("GitHub token not found. Set the GITHUB_TOKEN env var.")
REPO_OWNER = "8-K-bot"
REPO_NAME = "TEST" if TESTING else "8-Ks"
FILE_PATH = "8-Ks.md"
GITHUB_API_URL = (
    f"https://api.github.com/repos/{REPO_OWNER}/"
    f"{REPO_NAME}/contents/{FILE_PATH}"
)
MATERIAL = "Material*" if DETERMINE_MATERIALITY else "Material"
HEADING = f"""# List of Form 8-Ks with item {ITEM}
Last checked {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

|Form|Company|Timestamp|{MATERIAL}|Link|
|---|---|---|:---:|---|
"""
FOOTER = (
    "\n\n\\* Materiality is determined using OpenAI and may be inaccurate.\n"
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


# Set logging configuration
if TESTING:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(
        format='%(asctime)s %(levelname)-8s %(message)s',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S',
        force=True
    )


def trim_to_max_tokens(text, max_tokens=4096):
    """Trim OAI prompt to the maximum number of tokens."""

    # Get the encoding for the specified model
    encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")

    # Encode the text into tokens
    text_encoding = encoding.encode(text)

    # Get the number of tokens in the encoded text
    num_tokens = len(text_encoding)

    # If the number of tokens exceeds the maximum allowed,
    # trim the encoded text to the maximum number of tokens
    if num_tokens > max_tokens:
        text_encoding = text_encoding[:max_tokens]

        # Decode the trimmed encoding back into text
        text = encoding.decode(text_encoding)

    # Return the trimmed text
    return text


def is_the_incident_material(filing_text) -> str:
    """Use OAI to determine if the incident is material."""

    # Initialize the OAI client with your API key (will need to set)
    client = OpenAI(api_key=OPENAI_API_KEY)

    # Set full prompt
    with open('instructions.txt', 'r', encoding='utf-8') as file:
        oai_instructions = file.read()
    full_prompt = oai_instructions + filing_text

    # Trim prompt to the maximum number of tokens allowed by OAI
    trimmed_prompt = trim_to_max_tokens(full_prompt)

    # Define the message and send to the OAI API
    message = [{"role": "user", "content": trimmed_prompt}]
    response = client.chat.completions.create(
        messages=message,
        model="gpt-3.5-turbo",
    )

    # Extract the content of the first message in the response
    is_material = response.choices[0].message.content

    # Return "✓" if the incident is material, etc.
    return {"True": "✓", "False": "", "Unclear": "?"}.get(is_material, "?")


def extract_text(url) -> str:
    """Extracts and trims the text from the filing."""

    # Retrieve and parse the filing text
    response = requests.get(url, headers=SEC_HEADERS, timeout=10, stream=True)

    # Responses can be large, so we stream it and collect 1 KB at a time up to
    # a max of 0.5 MB. This is helpful for memory issues for large responses,
    # especially since the items generally appear near the top of the filing.
    mb = 0.5 * 1024 * 1024  # 0.5 MB
    content = b''
    for chunk in response.iter_content(chunk_size=1024):
        content += chunk
        if len(content) >= mb:
            break
    soup = BeautifulSoup(content, "lxml")
    text = soup.get_text()

    # Remove text above and below the relevant section
    # Hopefully this regex captures all real sections and not too much else
    start_substring = r"(?i)item[^>]{0,8}%s" % ITEM
    start_match = re.search(start_substring, text, re.IGNORECASE)
    start_index = start_match.start() if start_match else -1

    end_substring = r"forward[- ]?looking[- ]?statement"
    end_match = re.search(end_substring, text, re.IGNORECASE)
    end_index = end_match.start() if end_match else -1

    # Return the extracted text
    return text[start_index:end_index]


def get_sec_url(index: int) -> str:
    """Return the URL for the relevant 'latest filings' page."""
    return (
        "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent"
        "&datea=&dateb=&company=&type=8-k&SIC=&State=&Country=&CIK=&owner="
        f"include&accno=&start={index}&count={FILINGS_PER_PAGE}"
    )


def get_full_github_path():
    """Return full GitHub string for logs."""
    return f"{REPO_OWNER}/{REPO_NAME}/{FILE_PATH}"


def update_github_file(entries_to_file: str, current_sha: str) -> None:
    """Update the GitHub file with the latest Form 8-K entries."""

    # Set the content of the file to HEADING plus the entries
    full_content = HEADING
    full_content += entries_to_file if entries_to_file else ''
    full_content += FOOTER if DETERMINE_MATERIALITY else ''

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
        logging.info("Successfully updated %s.\n", get_full_github_path())
    elif response.status_code == 201:
        logging.info("Successfully created %s.\n", get_full_github_path())
    else:
        logging.error(
            "Error interacting with %s. HTTP Status Code: %s, Response: %s.\n",
            FILE_PATH,
            response.status_code,
            response.text
        )


def get_filing_info(element: tuple, last_checked: str) -> str:
    """Extract information from Form 8-K filing HTML element."""
    soup = BeautifulSoup(str(element[0]), 'html.parser')

    # Get the company name (assume that an <a> tag always exists in element[0])
    company = soup.find('a').get_text()
    company = re.sub(r'\([^)]*\) \(Filer\)\s*', '', company).strip()

    soup = BeautifulSoup(str(element[1]), 'html.parser')

    # Get timestamp (assume a <td> with a <br> always exists in element[1])
    date_time = (
        soup.find(
            lambda tag: tag.name == 'td' and tag.find('br'),
            {'nowrap': 'nowrap'}
        )
        .get_text()
    )
    date_time_obj = datetime.strptime(date_time, '%Y-%m-%d%H:%M:%S')
    date_time = date_time_obj.strftime("%Y-%m-%d %H:%M:%S")

    # If the filing is older than the last checked time, then it's presumably
    # already been analyzed, so we can skip it (and avoid OAI requests)
    if date_time <= last_checked:
        logging.info(
            "Skipping filing for %s as it's older than the last check.",
            company
        )
        return ''

    logging.info("Adding filing for %s.", company)

    # Get the URL to the actual form filing
    html_link = soup.find('a', string='[html]')
    url = f"https://www.sec.gov{html_link.get('href')}"

    # Determine if the incident is material
    if DETERMINE_MATERIALITY:
        text_url = url.replace("-index.htm", ".txt")
        text_of_the_filing = extract_text(text_url)
        is_material = is_the_incident_material(text_of_the_filing)
    else:
        is_material = "?"

    # Get the form type (8-K or 8-K/A)
    form_type = soup.find(
        'td', {'nowrap': 'nowrap'},
        string=re.compile(r'8-K(/A)?')
    ).get_text() or ''

    # Return the final row (incl. link)
    return f"|{form_type}|{company}|{date_time}|{is_material}|[link]({url})|\n"


def get_oldest_timestamp(text: str):
    """Return the timestamp of the first filing on the page"""

    pattern = re.compile(r'\d{4}-\d{2}-\d{2}\d{2}:\d{2}:\d{2}')
    ugly_oldest_on_page_string = pattern.findall(text)[0]
    oldest_on_page_obj = datetime.strptime(
        ugly_oldest_on_page_string,
        "%Y-%m-%d%H:%M:%S"
    )
    oldest_on_page_string = oldest_on_page_obj.strftime("%Y-%m-%d %H:%M:%S")
    return oldest_on_page_string


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

            tr_elements_with_item = []

            # Loop through all the rows on the page
            for prev_tr, current_tr in zip(tr_elements, tr_elements[1:]):
                text = current_tr.get_text()

                # Do stuff if we find a filing row (has "Current report")
                if "Current report" in text:
                    # Save the timestamp for the last filing on the page
                    oldest_filing_on_page = get_oldest_timestamp(text)
                    # If the filing has our item, save it for processing
                    if ITEM in text:
                        tr_elements_with_item.append((prev_tr, current_tr))

            # For each filing with our item, extract data if it's new
            for tr_element in tr_elements_with_item:
                relevant_filings += get_filing_info(
                    tr_element,
                    last_checked_datetime_string
                )

            # Break loop if we have already reviewed the page
            if last_checked_datetime_string >= oldest_filing_on_page:
                logging.info("Done extracting forms filed since last check.")
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
            filing_rows = []
            for line in current_content_as_strings:
                if line.startswith('|8-K'):
                    filing_rows.append(line)

            # Get the datetime of the last check -- this is to avoid
            # analyzing SEC pages that we've already reviewed
            if current_content_as_strings:
                last_checked = re.search(
                    r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}',
                    current_content_as_strings[1]
                ).group()
            else:
                last_checked = '1970-01-01 00:00:00'

            return filing_rows, current_sha, last_checked

        logging.info("%s doesn't exist, so creating it.", FILE_PATH)
        return None, None, '1970-01-01 00:00:00'

    except requests.exceptions.RequestException as exception:
        logging.error(
            "An error occurred during the request: %s.", str(exception)
        )
        return None, None, '1970-01-01 00:00:00'


def get_final_string(new_entries: list, old_entries: list) -> str:
    """Create the final str of filings; combine new and old lists if needed"""

    # If there are no existing filings, then the full list is just the new list
    if not old_entries:
        final_list = new_entries
    else:
        cutoff = old_entries[0].split('|')[3]
        final_list = [
            entry for entry in new_entries if entry.split('|')[3] > cutoff
        ]
        final_list += old_entries

    # If there are new entries, create a GitHub issue (for email notification)
    if len(final_list) > len(old_entries or []):
        create_github_issue()

    return '\n'.join(final_list)


def create_github_issue():
    """Create an issue in the GitHub repo to trigger an email notification."""

    logging.info("Creating GitHub issue in %s.", get_full_github_path())

    # Create the issue
    payload = {
        "title": "List of 8-Ks updated",
        "body": (
            "List of 8-Ks updated -- see [here]"
            f"(https://www.github.com/{REPO_OWNER}/{REPO_NAME}/"
            f"blob/main/{FILE_PATH})."
        ),
        "labels": ["Form 8-Ks"]
    }
    response = requests.post(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/issues",
        headers=GITHUB_HEADERS,
        json=payload,
        timeout=10
    )

    # Log the response
    if response.status_code == 201:
        logging.info("Successfully created issue.")
    else:
        logging.error(
            "Error creating issue. HTTP Status Code: %s, Response: %s.",
            response.status_code,
            response.text
        )


def main():
    """Main function to check and update the Form 8-K entries on GitHub."""

    # Get existing filings as a list of strings (one filing per string)
    # If there are existing entries, get the sha (needed to update a file)
    logging.info("Retrieving existing data from %s.", get_full_github_path())
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
    logging.info("Updating %s.", get_full_github_path())
    update_github_file(all_entries_string, current_sha)


if __name__ == "__main__":
    main()
