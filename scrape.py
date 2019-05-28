# -*- coding: utf-8 -*-

import time
import sys
import os
import re
import glob
import json
import requests
from bs4 import BeautifulSoup
from pprint import pprint
from tqdm import tqdm

# import requests_cache
# requests_cache.install_cache("test_cache",backend="sqlite",expire_after=1e6)

def get_usernames_in_html(text):
    return set(re.findall(r'="/profile/(\w+)"', text))

def get_usernames_from_forum_page(page=1):
    r = requests.get("https://mydramalist.com/discussions/general-discussion?page={}".format(page))
    return get_usernames_in_html(r.text)

def get_member_overview_dict(text):
    soup = BeautifulSoup(text, "html.parser")
    profile = {}
    for elem in soup.findAll(class_="list-item p-a-0"):
        t = elem.text
        k,v = t.split(":",1)
        k = k.replace(" ","_").lower().strip()
        v = v.strip()
        profile[k] = v
    return profile

def get_drama_rows(trs):
    dramas = []
    for drama in trs:
        tds = drama.findAll("td")
        country = tds[1].text.strip()
        year = int(tds[2].text.strip())
        kind = tds[3].text.strip()
        score = float(tds[4].text.strip())
        ep_seen,ep_total = map(int,tds[5].text.replace("?","-1").split("/"))
        atitle = tds[0].find("a")
        tid = int(atitle["data-info"].split(":")[1])
        title = atitle["title"]
        dramas.append(dict(
            country=country,
            year=year,
            kind=kind,
            score=score,
            ep_seen=ep_seen,
            ep_total=ep_total,
            tid=tid,
            title=title,
            ))
    return dramas


def get_user_info(username):

    r = requests.get("https://mydramalist.com/profile/{}".format(username))
    friends = sorted(set(get_usernames_in_html(r.text))-set([username]))
    overview_info = get_member_overview_dict(r.text)

    r = requests.get("https://mydramalist.com/dramalist/{}".format(username))
    soup = BeautifulSoup(r.text, "html.parser")
    category_names = map(lambda x:x.text.strip().lower().replace(" ","_"), soup.findAll("div",{"class":"box-header"}))

    completed_info = {}
    if "completed" in category_names:
        idx_completed = category_names.index("completed")
        trs = soup.findAll("tbody")[idx_completed].findAll("tr")
        completed_info = get_drama_rows(trs)

    dropped_info = {}
    if "dropped" in category_names:
        idx_dropped = category_names.index("dropped")
        trs = soup.findAll("tbody")[idx_dropped].findAll("tr")
        dropped_info = get_drama_rows(trs)


    user_info = {
            "username": username,
            "completed": completed_info,
            "dropped": dropped_info,
            "overview": overview_info,
            "friends": friends,
            }

    return user_info

def save_users(usernames):
    usernames = sorted(usernames)
    for username in tqdm(usernames):
        fname = "users/{}.json".format(username)
        if os.path.exists(fname): 
            print "Skipping {} because {} exists already".format(username,fname)
            return
        with open(fname,"w") as fh:
            print "Fetching {}".format(username)
            try:
                j = get_user_info(username)
                json.dump(j,fh)
                print "Dumped users/{}.json".format(username)
            except KeyboardInterrupt:
                print "[!] Exiting because of <C-c>"
                sys.exit()
            except:
                print "[!] Exception for {}".format(username)
                continue

def save_users_from_forums():
    # Get seed list of usernames from first ~100 forum pages
    tot_usernames = set()
    for i in tqdm(range(0,130)):
        usernames = get_usernames_from_forum_page(i)
        tot_usernames.update(usernames)
    save_users(tot_usernames)

def save_friends_of_saved_users():
    # compile list of friends of all the user jsons we've downloaded
    tot_usernames = set([])
    for x in tqdm(glob.glob("users/*.json")):
        try:
            tot_usernames.update(json.load(open(x))["friends"])
        except:
            pass
    # subtract out the ones we've already fetched
    tot_usernames -= set(map(lambda x:x.rsplit("/",1)[1].rsplit(".",1)[0],glob.glob("users/*.json")))
    save_users(tot_usernames)

def save_users_from_recently_seen():
    for ipage in range(1,50):

        try:
            r = requests.get("https://mydramalist.com/search?adv=titles&ty=68&co=3&re=2011,2019&ep=,&rt=6,10&st=3&so=newest&page={}".format(ipage))
            soup = BeautifulSoup(r.text, "html.parser")
        except:
            print "[!] Couldn't get page {}".format(ipage)
            continue

        for ih6,h6 in enumerate(soup.findAll("h6",{"class": "text-primary title"})):
            print "Page {}, show #{}, name {}".format(ipage,ih6,h6.text.strip())
            href = h6.find("a")["href"]
            try:
                r = requests.get("https://mydramalist.com{}".format(href))
                soup = BeautifulSoup(r.text, "html.parser")
            except:
                print "[!] Couldn't get {}".format(href)
                continue

            try:
                spans = soup.find("div",{"class":"box-watched-by"}).findAll("span")
            except AttributeError:
                continue

            usernames = set([span["data-href"].rsplit("/",1)[1] for span in spans])
            save_users(usernames)


if __name__ == "__main__":

    os.system("mkdir -p users/")

    # Save users from forum posts
    save_users_from_forums()

    # Save users from the recently seen list for various shows
    save_users_from_recently_seen()

    # Then save the friends of the currently saved users...recursively
    # About 4 iterations gives diminishing returns
    # You end up with nearly ~30k users
    for i in range(4):
        save_friends_of_saved_users()
