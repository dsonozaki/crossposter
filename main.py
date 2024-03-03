import asyncio
import logging
import os
import traceback
from aiogram import Bot as tBot
from aiogram.types import InputMediaPhoto, InputMediaDocument
from vkbottle.bot import Bot
from vkbottle_types import GroupTypes
from vkbottle_types.events import GroupEventType, WallPostNew
from vkbottle_types.objects import WallPostType
from dotenv import load_dotenv
import re

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
LONGPOLL_TOKEN = os.getenv("LONGPOLL_TOKEN")

poster = tBot(BOT_TOKEN)
seeker = Bot(
  token=LONGPOLL_TOKEN)
logging.basicConfig(level=logging.WARNING, filename='./crosspost_log.txt',
                    format='%(asctime)s %(levelname)s:%(message)s')

#Получение ссылки на фото с макcимальным разрешением
async def getLink(links):
  return max(links, key=lambda x: x.height).url

#получение InputMediaPhoto
async def getPhoto(i, photo, text=None):
  try:
    link = await getLink(photo)
    return InputMediaPhoto(link, caption=text if text is not None and i == 0 else '')
  except:
    logging.warning(f"проблемы с получением фотографии {photo.url}")
    logging.warning(traceback.format_exc())

#получение InputMediaDocument
async def getDoc(i, doc, text=None):
  try:
    return InputMediaDocument(doc.url)
  except:
    logging.warning(f"проблемы с получением документа {doc.url}")
    logging.warning(traceback.format_exc())

#получение группы документов или фото для отправки
async def getMediaPost(function, data, text=None):
  tasks = [function(i, data[i], text) for i in range(0, len(data))]
  results_group = await asyncio.gather(*tasks)
  return [element for element in results_group if element is not None]

#разделение слишком больших абзацев на предложения
async def splitPostBySentences(text, start):
  splited = re.findall('[^!?. ]+[!?.]+',text)
  for part in splited:
    newResult = start + " " + part
    if len(newResult) > 4096:
      try:
        await poster.send_message(CHAT_ID, start)
      except:
        logging.warning(f"не отправился большой текст \n {text}")
      start = part
      continue
    start = newResult
  return start

#разделение слишком больших постов на маленькие по абзацам.
async def splitPost(text):
  splited = text.split("\n")
  result = ""
  for part in splited:
    if len(part) > 4096:
      result = await splitPostBySentences(part, result + "\n")
      continue
    newResult = result + "\n" + part
    if len(newResult) > 4096:
      try:
        await poster.send_message(CHAT_ID, result)
      except:
        logging.warning(f"не отправился большой текст \n {text}")
      result = part
      continue
    result = newResult
  if len(result) != 0:
    await poster.send_message(CHAT_ID, result)

#отправка текста
async def textPost(text):
  try:
    if len(text) > 4096:
      await splitPost(text)
      return
    await poster.send_message(CHAT_ID, text)
  except:
    logging.warning(f"не отправился текст \n {text}")
    logging.warning(traceback.format_exc())

#отправка файлов
async def postMedia(docs, photos, text=None):
  coroutines = []
  documents = []
  if photos:
    coroutines.append(getMediaPost(getPhoto, photos, text))
  if docs:
    for doc in docs:
      if doc.ext == "gif":
        coroutines.append(getMediaPost(getDoc, [doc]))
        continue
      documents.append(doc)
  if documents:
    coroutines.append(getMediaPost(getDoc, documents))
  result = await asyncio.gather(*coroutines)
  print(result)
  for group in result:
    try:
      await poster.send_media_group(CHAT_ID, group)
    except:
      logging.warning(f"проблемы с отправкой медиа")
      logging.warning(traceback.format_exc())

#отправка поста, разбиение на текст, файлы, опрос
async def post(event):
  photos = []
  docs = []
  poll = None
  text = event.object.text
  if event.object.attachments is not None:
    for attachment in event.object.attachments:
      if attachment.link is not None:
        text += f" \n \nСтатья: {attachment.link.url}"
      if attachment.photo is not None:
        photos.append(attachment.photo.sizes)
      if attachment.video is not None:
        text += f" \n \nВидео: https://vk.com/video{attachment.video.owner_id}_{attachment.video.id}"
      if attachment.audio is not None:
        "Здесь когда-нибудь может быть метод для скачивания аудио из вк"
      if attachment.doc is not None:
        docs.append(attachment.doc)
      if attachment.poll is not None:
        poll = attachment.poll
  if event.object.copyright:
    text += f" \n \nИсточник: {event.object.copyright.link}"
  if not photos and not docs:
    await textPost(text)
  else:
    if len(text) > 1024:
      await textPost(text)
      await postMedia(docs, photos)
    else:
      await postMedia(docs, photos, text)
  if poll is not None:
    answers = [a.text for a in poll.answers]
    try:
      await poster.send_poll(CHAT_ID, question=poll.question, options=answers, allows_multiple_answers=poll.multiple)
    except:
      logging.warning("опрос не отправился")
      logging.warning(traceback.format_exc())

#получение уведомления о посте
@seeker.on.raw_event(GroupEventType.WALL_POST_NEW, dataclass=GroupTypes.WallPostNew)
async def postHandler(event: WallPostNew):
  logging.warning("New event!")
  if event.object.post_type == WallPostType.POST and not event.object.donut.is_donut:
    await post(event)


seeker.run_forever()
