import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import perf_counter, time, localtime, strftime
from re import sub
from threading import Thread
from email.mime.text import MIMEText
import smtplib, ssl
import json

start_time = perf_counter()

HEIGHT = 32
MAX_ITERATIONS = 25 # failsafe if stop_rowid = [], DEFAULT: 75 TESTING: 10
SAVE_ROWS = 5 # rows to save for to check aganist for next run
GAP = 2
DELIM = " " * GAP + "|" + " " * GAP

WHITELIST_SIZES = ('1001-5000', '5001-10000', '10000+')
SPACE = {"akshat.wajge@gmail.com": {"title": 60, "company": 25, "date": 10, "location": 20, "tags": 40},
         "nishad.wajge@gmail.com": {"title": 85, "company": 35, "date": 10, "location": 20, "tags": 55}}

port = 465
smtp_server = "smtp.gmail.com"
USERNAME = os.environ.get('USER_EMAIL')
PASSWORD = os.environ.get('USER_PASSWORD')
RECIPIENTS = os.environ.get('RECIPIENTS')

internships = {} # link: (name, [{"title": title, "company" company ...}, {...} ...])
save_data = {}

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

def get_innertext(driver, row, category, div_class="truncate", multiple=False): # multiple=True means a list
    matches = [
        match.get_attribute("innerText")
        for match in row.find_element(By.CSS_SELECTOR, f'div[data-columnindex="{find_columnindex(driver, category)}"]') \
                    .find_elements(By.CSS_SELECTOR, f"div.{div_class}") \
    ]

    return matches if multiple else (matches[0] if matches != [] else None)

def append_data(driver, row): # data to be emailed
    row_id = row.get_attribute("data-rowid")
    
    title = get_innertext(driver, driver.find_element(By.CSS_SELECTOR, f'div[data-rowid="{row_id}"]'), "Position Title") # in leftPane not right
    company = get_innertext(driver, row, "Company")
    date = get_innertext(driver, row, "Date")
    location = get_innertext(driver, row, "Location")
    tags = get_innertext(driver, row, "Company Industry", "flex-auto.truncate-pre", True)
    apply_link = row.find_element(By.CSS_SELECTOR, "span.truncate.noevents").find_element(By.XPATH, "..").get_attribute("href") # get parent's href

    if "Multi Location" in location: location = "Multi Location"
    if tags == []: tags.append("None")

    return {"title": title, "company": company, "date": date, "location": location, "tags": tags, "apply_link": apply_link}

def find_columnindex(driver, category): # column indexes differ per page
    return driver.find_element(By.XPATH, f'//div[text()="{category}"]').find_element(By.XPATH, "../../../../../..").get_attribute("data-columnindex")

def add_internships(link, attempts=1):
    with open("save_data.json", "r") as f: # migrate out of function?
        try: stop_data = json.load(f)[link]
        except: stop_data = []

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1920, 1080) # necessary for tags to be rendered
    driver.set_page_load_timeout(10)
    wait = WebDriverWait(driver, 10)

    try: driver.get(link)
    except: add_internships(link, attempts+1) 
    wait.until(EC.presence_of_element_located((By.ID, "airtable-box")))

    list_name = driver.find_element(By.CSS_SELECTOR, "h2.active").get_attribute("innerText")

    airtable_url = driver.find_element(By.ID, "airtable-box").get_attribute("src")
    try: driver.get(airtable_url)
    except: add_internships(link, attempts+1)
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dataRow.rightPane.rowExpansionEnabled.rowSelectionEnabled")))

    scrollable = driver.find_element(By.CSS_SELECTOR, "div.antiscroll-inner")
    elements = driver.find_elements(By.CSS_SELECTOR, "div.dataRow.rightPane.rowExpansionEnabled.rowSelectionEnabled")

    local_dict = {}
    finished = False
    row_count = 0

    while not finished:
        if row_count < len(elements) - 1:
            row = elements[row_count]
        else:
            row = driver.find_elements(By.CSS_SELECTOR, "div.dataRow.rightPane.rowExpansionEnabled.rowSelectionEnabled")[-1] # reload elements
            driver.execute_script(f"arguments[0].scrollTop += {HEIGHT};", scrollable)

        row_data = append_data(driver, row)

                                            # testing purposes: (len(local_dict) == 10 and stop_data == []) or 
        if (row_data["apply_link"] in stop_data) or (len(local_dict) == MAX_ITERATIONS):
            finished = True # switch while loop condition?
        elif get_innertext(driver, row, "Company Size", "flex-auto.truncate-pre") in WHITELIST_SIZES:
            local_dict[row.get_attribute("data-rowid")] = row_data
        
        row_count += 1


    save_data[link] = ([r["apply_link"] for r in list(local_dict.values())[:SAVE_ROWS]] + stop_data)[:SAVE_ROWS] # saves the most recent rows

    internships[link] = {"category": list_name, "links": list(local_dict.values())}

    print(f'Thread of "{link}" processed in {(perf_counter() - start_time):.3f} seconds & {attempts} attempt(s)')
    driver.close()

#def check_link(link):
#    driver = webdriver.Chrome(options=options)
#    driver.set_window_size(1920, 1080)
#    wait = WebDriverWait(driver, 20)

def format(data, custom_space, on_watchlist, in_cali):
    link_sub = truncate(data["title"], custom_space["title"], False).strip()
    line = (f'<a href="{data["apply_link"]}" target="_blank">{link_sub}</a>') + (' ' * (custom_space["title"] - len(link_sub)) + DELIM) # clickable position title
    line += truncate(data["company"], custom_space["company"])
    line += truncate(data["date"], custom_space["date"])
    line += truncate(data["location"], custom_space["location"])
    line += truncate(", ".join(str(tag) for tag in data["tags"]), custom_space["tags"], False)

    line = f'<span style="background-color: #c8f7c5;">{line}</span>' if (on_watchlist) else line
    line = f'<span style="background-color: #fff8b3;">{line}</span>' if (in_cali) else line

    return line + "\n"

def truncate(string, num, part=True):
    return string.ljust(num)[:num] + (DELIM if part else " " * GAP)

with open("links.json", "r") as f:
    try: internship_links = json.load(f) # internships_links doubles as the priority list (is sorted)
    except: internship_links = []

threads = []
for link in internship_links:
    t = Thread(target=add_internships, args=(link,))
    threads.append(t)
    t.start()

[t.join() for t in threads] # waits until all threads finish

#with open("save_data.json", "w") as f:
    #json.dump(save_data, f, indent=4)

with open("watchlist.json", "r") as f:
    try: watchlist = json.load(f)
    except: watchlist = []

def make_message(recipient):
    message_text = ""
    for link in internship_links + [k for k in internships if k not in internship_links]:
        try: link_data = internships[link]
        except: continue

        text_subsection = ""
        priority_entries = []
        instate_entries = []
        regular_entries = []
        for data in link_data["links"]:
            on_watchlist = data["company"].strip() in watchlist
            in_cali = any(match in data["location"] for match in ["CA", "California"])

            (priority_entries if on_watchlist else (instate_entries if in_cali else regular_entries)).append(format(data, SPACE[recipient], on_watchlist, in_cali))

        text_subsection += "".join(priority_entries)
        text_subsection += "\n".join(instate_entries)
        text_subsection += "\n".join(regular_entries)

        text_subsection = f'\n===== From: <a href="{link}" target="_blank">{sub(r"[^a-zA-Z0-9 ]+", "", link_data["category"]).strip()}</a> ({len(link_data["links"])}) =====\n\n' + text_subsection
        message_text += text_subsection

    message = MIMEText(f'<pre style="font-family: monospace;">{message_text}</pre>', 'html')

    message['Subject'] = f"Intern Bot 🤖 : {sum(len(data['links']) for data in internships.values())} internships found on {strftime('%m/%d/%Y', localtime(time()))}"
    message["From"] = USERNAME
    message["To"] = recipient

    return message.as_string()

context = ssl.create_default_context()
with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
    server.login(USERNAME, PASSWORD)
    for recipient in RECIPIENTS.split(","): server.sendmail(USERNAME, recipient, make_message(recipient.strip()))
    print(f"Message sent to {recipient} in {(perf_counter() - start_time):.3f} seconds")