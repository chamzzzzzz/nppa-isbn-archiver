from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import NoSuchElementException
from selenium_stealth import stealth
from dataclasses import dataclass, field
from typing import List, Optional
from dataclasses_json import dataclass_json, config
from email.header import Header
import argparse
import logging
import os
import datetime
import smtplib
import re

ChannelImportOnlineGameApprovaled = "jkwlyxspxx"
ChannelImportElectronicGameApprovaled = "jkdzyxspxx"
ChannelMadeInChinaOnlineGameApprovaled = "gcwlyxspxx"
ChannelGameChanged = "yxspbgxx"
ChannelGameRevoked = "yxspcxxx"

ChannelChineseNames = {
    ChannelImportOnlineGameApprovaled: "进口网络游戏审批信息",
    ChannelImportElectronicGameApprovaled: "进口电子游戏审批信息",
    ChannelMadeInChinaOnlineGameApprovaled: "国产网络游戏审批信息",
    ChannelGameChanged: "游戏审批变更信息",
    ChannelGameRevoked: "游戏审批撤销信息",
}

@dataclass_json
@dataclass
class Item:
    seq: Optional[str] = None
    name: Optional[str] = None
    catalog: Optional[str] = field(default=None, metadata=config(exclude=lambda x: not x))
    publisher: Optional[str] = field(default=None, metadata=config(exclude=lambda x: not x))
    operator: Optional[str] = field(default=None, metadata=config(exclude=lambda x: not x))
    approval_number: Optional[str] = field(default=None, metadata=config(field_name="approvalNumber", exclude=lambda x: not x))
    isbn: Optional[str] = field(default=None, metadata=config(exclude=lambda x: not x))
    date: Optional[str] = field(default=None, metadata=config(exclude=lambda x: not x))
    change_info: Optional[str] = field(default=None, metadata=config(field_name="changeInfo", exclude=lambda x: not x))
    revoke_info: Optional[str] = field(default=None, metadata=config(field_name="revokeInfo", exclude=lambda x: not x))

@dataclass_json
@dataclass
class Content:
    title: Optional[str] = None
    url: Optional[str] = None
    date: Optional[str] = None
    items: List[Item] = None

class NotFound404Exception(Exception):
    pass

def get_page_contents(driver, page):
    contents = []
    suffix = f"_{page}" if page > 0 else ""
    url = f"https://www.nppa.gov.cn/bsfw/jggs/yxspjg/index{suffix}.html"

    driver.get(url)
    WebDriverWait(driver, 30).until(lambda driver: "国家新闻出版署" == driver.title)

    try:
        driver.find_element(By.CSS_SELECTOR, "div.g-font-size-140.g-font-size-100--2xs.g-line-height-1.g-mb-10")
        raise NotFound404Exception()
    except NoSuchElementException:
        pass

    lis = driver.find_elements(By.CSS_SELECTOR, "div.m2nRcon > ul > li")
    for li in lis:
        a = li.find_element(By.CSS_SELECTOR, "a")
        span = li.find_element(By.CSS_SELECTOR, "span")
        href = a.get_attribute("href")
        content = Content(
            title=a.text.strip(),
            url=href.strip() if href else "",
            date=span.text.strip("[]")
        )
        contents.append(content)
    return contents

def get_channel(url):
    parts = url.replace('https://www.nppa.gov.cn/bsfw/jggs/yxspjg/', '').split("/")
    return parts[0] if len(parts) == 3 else ""

def get_items(driver, content):
    driver.get(content.url)
    WebDriverWait(driver, 30).until(lambda driver: "国家新闻出版署" == driver.title)

    channel = get_channel(content.url)
    items = []
    for tr in driver.find_elements(By.CSS_SELECTOR, "tr.item"):
        td = tr.find_elements(By.CSS_SELECTOR, "td")
        item = Item()
        item.seq = td[0].text.strip()
        item.name = td[1].text.strip()
        if channel == ChannelImportElectronicGameApprovaled:
            if len(td) != 5:
                raise Exception("item field len error")
            item.publisher = td[2].text.strip()
            item.approval_number = td[3].text.strip()
            item.date = td[4].text.strip()
        elif channel in [ChannelImportOnlineGameApprovaled, ChannelMadeInChinaOnlineGameApprovaled]:
            fc = len(td)
            if fc != 7 and fc != 8:
                raise Exception("item field len error")
            if fc == 8:
                item.catalog = td[2].text.strip()
                item.publisher = td[3].text.strip()
                item.operator = td[4].text.strip()
                item.approval_number = td[5].text.strip()
                item.isbn = td[6].text.strip()
                item.date = td[7].text.strip()
            else:
                script = tr.find_element(By.CSS_SELECTOR, "script")
                matches = re.compile(r"var _sblb = '(.*)';").findall(script.get_attribute("innerHTML").replace("\n", ""))
                if len(matches) != 1:
                    raise Exception("item field script error")
                item.catalog = matches[0]
                item.publisher = td[2].text.strip()
                item.operator = td[3].text.strip()
                item.approval_number = td[4].text.strip()
                item.isbn = td[5].text.strip()
                item.date = td[6].text.strip()
        elif channel == ChannelGameChanged:
            if len(td) != 8:
                raise Exception("item field len error")
            item.catalog = td[2].text.strip()
            item.publisher = td[3].text.strip()
            item.operator = td[4].text.strip()
            item.change_info = td[5].text.strip()
            item.approval_number = td[6].text.strip()
            item.date = td[7].text.strip()
        elif channel == ChannelGameRevoked:
            if len(td) != 9:
                raise Exception("item field len error")
            item.catalog = td[2].text.strip()
            item.publisher = td[3].text.strip()
            item.operator = td[4].text.strip()
            item.revoke_info = td[5].text.strip()
            item.approval_number = td[6].text.strip()
            item.isbn = td[7].text.strip()
            item.date = td[8].text.strip()
        items.append(item)
    return items

def main():
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--headless', action='store_true', help='webdriver headless')
    parser.add_argument('--full', action='store_true', help='full archive')
    parser.add_argument('--addr', default=os.getenv("ISBN_SMTP_ADDR"), help='notification smtp addr')
    parser.add_argument('--user', default=os.getenv("ISBN_SMTP_USER"), help='notification smtp user')
    parser.add_argument('--pass', default=os.getenv("ISBN_SMTP_PASS"), help='notification smtp pass', dest="passwd")
    parser.add_argument('--to', default=os.getenv("ISBN_SMTP_TO"), help='notification smtp to')
    args = parser.parse_args()

    logging.basicConfig(format='%(asctime)s %(levelname)s %(message)s', level=logging.INFO)

    options = webdriver.ChromeOptions()
    options.page_load_strategy = 'eager'
    if args.headless:
        options.add_argument("--headless")
        options.add_argument("--window-size=1920,1080")

    logging.info('starting webdriver...')
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)
    stealth(
        driver,
        languages=["en-US", "en"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    logging.info('start webdriver success')

    page = 1
    if args.full:
        page = 30
        logging.info(f'full archive. page={page}')
    else:
        logging.info(f'increment archive. page={page}')

    bn = []
    for i in range(page):
        try:
            contents = get_page_contents(driver, i)
        except NotFound404Exception:
            break
        except Exception as e:
            logging.error(f'get page contents fail. page={i}, err={e}')
            return
        logging.info(f'get page contents success. page={i}, contents={len(contents)}')
        bn.extend(contents)
    logging.info(f'get contents success. contents={len(bn)}')

    newbn = []
    for content in bn:
        p = f'data/{content.title}.json'
        try:
            c, skip = should_skip(p, content)
            if skip:
                logging.info(f'skip archived content. title={content.title}, path={p}')
                continue
        except Exception as e:
            logging.error(f'should skip fail. title={content.title}, path={p}, err={e}')
            return

        try:
            items = get_items(driver, content)
            content.items = items
            logging.info(f'get content items success. title={content.title}, items={len(items)}')
        except Exception as e:
            logging.error(f'get content items fail. title={content.title}, err={e}')
            return

        if len(content.items) == 0:
            logging.info(f'skip empty content. title={content.title}')
            continue
        if not diff(c, content):
            logging.info(f'skip same content. title={content.title}')
            continue
        newbn.append(content)

    try:
        os.mkdir("data")
    except FileExistsError:
        pass
    except Exception as e:
        logging.error(f'mkdir data fail. err={e}')
        return

    for content in newbn:
        p = f'data/{content.title}.json'
        try:
            write_content(p, content)
            logging.info(f'write content success. title={content.title}, path={p}')
        except Exception as e:
            logging.error(f'write content fail. title={content.title}, path={p}, err={e}')
            return

    if not args.full and len(newbn) > 0:
        notification(newbn, args.addr, args.user, args.passwd, args.to)

def should_skip(path, content: Content) -> tuple[Content, bool]:
    if not os.path.exists(path):
        return None, False
    channel = get_channel(content.url)
    if channel == ChannelMadeInChinaOnlineGameApprovaled:
        return None, True
    year = datetime.datetime.now().year
    if content.title.find(str(year)) == -1:
        return None, True
    return read_content(path), False

def diff(o, n: Content) -> bool:
    if o is None:
        return True
    if o.title != n.title:
        return True
    if o.url != n.url:
        return True
    if o.date != n.date:
        return True
    if len(o.items) != len(n.items):
        return True
    for i in range(len(o.items)):
        oi = o.items[i]
        ni = n.items[i]
        if oi.seq != ni.seq:
            return True
        if oi.name != ni.name:
            return True
        if oi.catalog != ni.catalog:
            return True
        if oi.publisher != ni.publisher:
            return True
        if oi.operator != ni.operator:
            return True
        if oi.approval_number != ni.approval_number:
            return True
        if oi.isbn != ni.isbn:
            return True
        if oi.date != ni.date:
            return True
        if oi.change_info != ni.change_info:
            return True
        if oi.revoke_info != ni.revoke_info:
            return True
    return False

def read_content(path) -> Content:
    with open(path, 'r', encoding='utf-8') as f:
        return Content.from_json(f.read())

def write_content(path, content: Content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.to_json(ensure_ascii=False, indent=2))

def notification(contents: list[Content], addr: str, user: str, passwd: str, to: str):
    logging.info("sending notification...")
    if not addr:
        logging.info("send notification skip. addr is empty")
        return

    _from = Header(f'Monitor <{user}>').encode()
    subject = Header('「ISBN」审批信息').encode()
    body = '\r\n\r\n'.join([f'{c.title} ({len(c.items)})\r\n{c.url}' for c in contents])
    msg = f'From: {_from}\r\nTo: {to}\r\nSubject: {subject}\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n{body}'

    try:
        host, port = addr.split(':')
        server = smtplib.SMTP_SSL(host, int(port))
        server.login(user, passwd)
        server.sendmail(user, to, msg.encode('utf-8'))
        server.quit()
        logging.info(f'send notification success.')
    except Exception as e:
        logging.error(f'send notification fail. err={e}')

if __name__ == "__main__":
    main()
