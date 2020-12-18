import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import time
from googleapiclient.http import MediaFileUpload
import requests
import uuid
import cv2
import numpy as np

DEVELOPER_KEY = "REPLACE WITH YOUR KEY"
CLIENT_SECRET = "REPLACE WITH PATH TO YOUR JSON"
VIDEO_ID = "REPLACE WITH VIDEO ID"
scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
youtube_comment = None
youtube_thumbnail = None
current_thumbnail = ""
name_list = []

def detected_chain(safe,likelihood_name):
    if likelihood_name[safe.adult] == 'VERY_UNLIKELY' and likelihood_name[safe.racy] == 'POSSIBLE' and likelihood_name[safe.medical] == 'UNLIKELY' and likelihood_name[safe.spoof] == 'UNLIKELY' and likelihood_name[safe.violence] == 'POSSIBLE':
        return True
    else:
        return False

def detect_safe_search(path):

    from google.cloud import vision
    import io
    client = vision.ImageAnnotatorClient()

    with io.open(path, 'rb') as image_file:
        content = image_file.read()

    image = vision.Image(content=content)
    response = client.safe_search_detection(image=image)
    safe = response.safe_search_annotation

    # Names of likelihood from google.cloud.vision.enums
    likelihood_name = ('UNKNOWN', 'VERY_UNLIKELY', 'UNLIKELY', 'POSSIBLE',
                       'LIKELY', 'VERY_LIKELY')

    adult_res = likelihood_name.index(likelihood_name[safe.adult])
    medical_res = likelihood_name.index(likelihood_name[safe.medical])
    spoof_res = likelihood_name.index(likelihood_name[safe.spoof])
    violence_res = likelihood_name.index(likelihood_name[safe.violence])
    racy_res = likelihood_name.index(likelihood_name[safe.racy])
    res_list = [adult_res,medical_res,spoof_res,violence_res,racy_res]

    print("DECODED RATINGS:",res_list)
    if res_list[0] >= 2: return False
    for res in res_list:
        if res >= 3: return False
    return True

def is_url_image(comment):
    comment = str(comment)
    image_url = ""
    try:
        keyword = "https"
        start_index = comment.index(keyword)
        for x in range(start_index,len(comment)):
            char = comment[x]
            if char == ' ' or char == '\n': break
            image_url += char

    except Exception as e:
        #print(e)
        return False

    try:
       image_formats = ("image/png", "image/jpeg", "image/jpg")
       r = requests.head(image_url)
       if r.headers["content-type"] in image_formats:
          return image_url
       return False
    except Exception as e:
        #print(e)
        return False

def filter_comments(comments):
    valid_comments = []
    for comment in comments:
        url = is_url_image(comment[0])
        if url != False:
            valid_comments.append((url,comment[1],comment[2]))

    return valid_comments

def process_comments():
    print("PROCESSING COMMENTS...")
    all_comments_with_like = []
    nextPageToken = None
    while True:
        request = youtube_comment.commentThreads().list(
            part="snippet",
            maxResults=100,
            videoId=VIDEO_ID,
            pageToken=nextPageToken
        )
        response = request.execute()
        items = [item for item in response['items']]
        comments = [item['snippet']['topLevelComment'] for item in items]
        comments_with_like = [(comment['snippet']['textOriginal'],comment['snippet']['likeCount'],comment['snippet']['authorDisplayName']) for comment in comments]
        filtered_comments_with_like = filter_comments(comments_with_like)
        for item in filtered_comments_with_like:
            all_comments_with_like.append(item)

        try:
            nextPageToken = response['nextPageToken']
        except:
            print("ERROR AT RESPONSE")
            break

    sorted_comments = sorted(all_comments_with_like, key=lambda x: x[1], reverse=True)
        ##------EDIT VIDEO THUMBNAIL TO HIGHEST-------##
    print("SORTED COMMENTS",sorted_comments)
    if len(sorted_comments) > 0 and sorted_comments[0][2] not in name_list and sorted_comments[0][0] != current_thumbnail:
        download_image_from_url(sorted_comments[0][0],sorted_comments[0][2])

def process_chosen_thumbnail(image_file):
    try:
        img = cv2.imread(image_file)
        img = cv2.resize(img, (889, 500))
        template = cv2.imread('thumbnail_template.png')
        result = template
        h, w, channel = img.shape

        h_start = 50
        w_start = 50

        for i in range(h):
            for j in range(w):
                color2 = img[i, j]
                new_color = [color2[0], color2[1], color2[2]]
                result[i + h_start, j + w_start] = new_color

        os.remove(image_file)
        cv2.imwrite('images/processed.png', result)
        print("PROCESSED IMAGE!")
        return 'images/processed.png'
    except:
        print("ERROR AT PROCESSING THUMBNAIL")

def edit_video_thumbnail(image_file,url,name):

    global current_thumbnail
    image_file = process_chosen_thumbnail(image_file)
    print("IMAGE FILE IS",image_file)

    request = youtube_thumbnail.thumbnails().set(
        videoId=VIDEO_ID,
        media_body=MediaFileUpload(image_file)
    )
    attempts = 0
    attempt_cap = 5
    while True:
        if attempts > attempt_cap:
            break
        try:
            response = request.execute()
            print(response)
            update_name_list(name)
            current_thumbnail = url
            os.remove(image_file)
            break
        except:
            print("ERROR AT EDITING THUMBNAIL")
            attempts += 1
            time.sleep(2)

def download_image_from_url(url,name):
    try:
        print("DOWNLOADING:",url)
        response = requests.get(url)
        file_name = 'images/'+str(uuid.uuid1())+'.png'
        file = open(file_name,"wb")
        file.write(response.content)
        file.close()

        if detect_safe_search(file_name):
            edit_video_thumbnail(file_name,url,name)
    except:
        print("ERROR DOWNLOADING IMAGE")

def setup_youtube_api():
    global youtube_thumbnail
    global youtube_comment

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "avian-silicon-293713-6a002bb5f414.json"
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"
    api_service_name = "youtube"
    api_version = "v3"
    client_secrets_file = CLIENT_SECRET

    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes)
    credentials = flow.run_console()

    #-----YOUTUBE THUMBNAIL------#
    youtube_thumbnail = googleapiclient.discovery.build(
        api_service_name, api_version, credentials=credentials)

    #-----YOUTUBE COMMENT------#
    youtube_comment = googleapiclient.discovery.build(
        api_service_name, api_version, developerKey = DEVELOPER_KEY)


def read_name_list():
    global name_list
    try:
        with open("name.txt", "r") as name_file:
            content = name_file.read()
            name_list = content.split('%')
            print(name_list)
    except:
        print("ERROR AT READ NAME")

def update_name_list(name):
    try:
        with open("name.txt","a") as name_file:
            name_file.write("%"+name)
        read_name_list()
    except:
        print("ERROR AT UPDATE_NAME_LIST")


def main():
    read_name_list()
    minutes = 10
    setup_youtube_api()
    process_comments()
    start = int(round(time.time()*1000))
    display_start = start
    print("CURRENT THUMBNAIL:" + current_thumbnail)
    while True:
        try:
            now = int(round(time.time()*1000))
            if now - start > minutes * 60 * 1000:
                print("PROCESSING COMMENTS...")
                start = now
                process_comments()
            if now - display_start > 10*1000:
                display_start = now
                print("CURRENT THUMBNAIL:" + current_thumbnail)
        except: print("ERROR AT MAIN")

main()

