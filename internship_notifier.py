import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from time import perf_counter, time, localtime, strftime
from email.mime.text import MIMEText
import smtplib, ssl
import threading
import json

start_time = perf_counter()

HEIGHT = 32
MAX_ITERATIONS = 10 # failsafe if stop_rowid = []
SAVE_ROWS = 5 # rows to save for to check aganist for next run
GAP = 5

port = 465
smtp_server = "smtp.gmail.com"
USERNAME = os.environ.get('USER_EMAIL')
PASSWORD = os.environ.get('USER_PASSWORD')
RECIPIENTS = os.environ.get('RECIPIENTS')

internships = {} # link: [[title, company, date, location, tags, apply_link], [...] ...]
save_data = {}

options = Options()
options.add_argument("--headless=new")
options.add_argument("--no-sandbox")
options.add_argument("--disable-dev-shm-usage")

def get_innertext(row, columnindex, div_class="truncate", multiple=False):
    matches = [
        match.get_attribute("innerText")
        for match in row.find_element(By.CSS_SELECTOR, f'div[data-columnindex="{columnindex}"]') \
                    .find_elements(By.CSS_SELECTOR, f"div.{div_class}") \
    ]

    return matches if multiple else matches[0]

def append_data(driver, row): # data to be emailed
    row_id = row.get_attribute("data-rowid")
    
    title = get_innertext(driver.find_element(By.CSS_SELECTOR, f'div[data-rowid="{row_id}"]'), find_columnindex(driver, "Position Title")) # in leftPane not right
    company = get_innertext(row, find_columnindex(driver, "Company"))
    date = get_innertext(row, find_columnindex(driver, "Date"))
    location = get_innertext(row, find_columnindex(driver, "Location"))
    tags = get_innertext(row, find_columnindex(driver, "Company Industry"), "flex-auto.truncate-pre", True)
    apply_link = row.find_element(By.CSS_SELECTOR, "span.truncate.noevents").find_element(By.XPATH, "..").get_attribute("href") # get parent's href

    if tags == []: tags.append("None")

    return (title, company, date, location, tags, apply_link)

def find_columnindex(driver, category): # column indexes differ per page
    return driver.find_element(By.XPATH, f'//div[text()="{category}"]').find_element(By.XPATH, "../../../../..").get_attribute("data-columnindex")

def add_internships(link):
    with open("save_data.json", "r") as f:
        try: stop_data = json.load(f)[link]
        except: stop_data = []

    driver = webdriver.Chrome(options=options)
    driver.set_window_size(1920, 1080) # necessary for tags to be rendered
    wait = WebDriverWait(driver, 20)

    driver.get(link)
    list_name = driver.find_element(By.CSS_SELECTOR, "h2.active")

    airtable_url = driver.find_element(By.ID, "airtable-box").get_attribute("src")
    driver.get(airtable_url)

    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.dataRow.rightPane.rowExpansionEnabled.rowSelectionEnabled")), "timeout on airtable")

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

        if (row_data[5] in stop_data) or (row_count == MAX_ITERATIONS and stop_data == []): # row_data[5] = apply link
            finished = True
        else:
            local_dict[row.get_attribute("data-rowid")] = row_data
        
        row_count += 1


    # save_data[link] = ([x[5] for x in list(local_dict.values())[:SAVE_ROWS]] + stop_data)[:SAVE_ROWS] # saves the most recent rows

    internships[link] = list(local_dict.values())

    print(f'Thread of "{link}" processed in {(perf_counter() - start_time):.3f} seconds')
    driver.close()

def format(data):
    link_sub = truncate(data[0], 50).strip()
    line = (f'<a href="{data[5]}" target="_blank">{link_sub}</a>') + (' ' * (55 - len(link_sub)))   # clickable link; 79 = 50 + html chars
    line += truncate(data[1], 15)
    line += truncate(data[2], 10)
    line += truncate(data[3], 20)
    line += truncate(", ".join(str(tag) for tag in data[4]), 25).strip()

    return line

def truncate(string, num):
    return (string if len(string) < num else string[:num]).ljust(num + GAP)

with open("links.json", "r") as f:
    try: internship_links = json.load(f)
    except: internship_links = []

threads = []
for link in internship_links:
    t = threading.Thread(target=add_internships, args=(link,))
    threads.append(t)
    t.start()

[t.join() for t in threads] # waits until all threads finish

with open("save_data.json", "w") as f:
    json.dump(save_data, f, indent=4)

# 0 character max - 5 space, date, location (20), company (15), title (50), tags (25)
message_content = 5
message_datetime = strftime("at %H:%M:%S on %Y-%m-%d", localtime(time()))

message_text = ""
for link in internships.keys():
    message_text += f"\n===== From: {link} =====\n\n"
    for data in internships[link]:
        message_text += format(data) + "\n"

message = MIMEText(f'''<pre style="font-family: monospace; font-size: small;">{message_text}</pre>''', 'html')

message['Subject'] = f"{sum(map(len, internships.values()))} internships found from {len(internship_links)} links {message_datetime}"
message["From"] = USERNAME
message["To"] = RECIPIENTS

context = ssl.create_default_context()
with smtplib.SMTP_SSL(smtp_server, port, context=context) as server:
    server.login(USERNAME, PASSWORD)
    server.sendmail(USERNAME, [e.strip() for e in RECIPIENTS.split(",")], message.as_string())

print(f"Message sent in {(perf_counter() - start_time):.3f} seconds")