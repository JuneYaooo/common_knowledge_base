import logging
from celery import shared_task, current_task
from celery.result import AsyncResult
from celery.exceptions import Ignore
from django.core.cache import cache
import pandas as pd
import json
from common.qdrant_new import VectorDatabaseUpdater
from common.read_files import read_file, process_markdown,process_txt, list_files_in_folder, unzip_file, extract_pdf, read_docx, process_docx, extract_md_title, read_url, process_url, read_txt, process_txt
from common.llm_assist_rag import get_qa_chunk
from common.read_files import process_article
from django.conf import settings
import traceback
import shutil
import os
import random
import time


# 设置日志记录器
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_POST = os.getenv("QDRANT_POST")


@shared_task(name='update_database_async')
def update_database_async(user_id, conf_dict, temp_file_path, mode='normal', urls=[], article_text=None, article_metadata={}):
    logger.info(f'===in task==={mode}')
    task = current_task
    task.update_state(state='PROGRESS', meta={'message': 'Started'})
    try:
        try:
            conf_dict = json.loads(conf_dict) if conf_dict else {}
        except json.JSONDecodeError as e:
            logger.info('json.JSONDecodeError')
            exc_type = type(e).__name__
            logger.error('Invalid conf_dict: %s', e)
            task.update_state(state='FAILURE', meta={'exc_type': exc_type,'message': 'Invalid conf_dict: ' + str(e)})
            raise Ignore()
        file_extension = temp_file_path.split('.')[-1].lower() if temp_file_path != '' else 'urls' if (urls != [] and len(urls) > 0 and urls is not None) else 'article' if article_text != None else ''
        logger.info(f"file_extension {file_extension}")
        logger.info(f"temp_file_path {temp_file_path}")
        logger.info(f"import urls {urls}")
        # updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST, user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
        if user_id in settings.EMBEDDING_DB_MAPPING:
                if settings.EMBEDDING_DB_MAPPING[user_id]=='m3e-base':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.M3E_BASE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='e5-large':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.E5_LARGE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='bge-m3':
                    print('use_bge_m3!!!')
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.BGE_M3_EMBEDDING_MODEL)
                else:
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
        else:
            updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
        finished_file_list = []
        if mode == 'normal':
            print('MODE: normal')
            if file_extension in ('xlsx', 'xls'):
                # 处理Excel文件
                xls = pd.ExcelFile(temp_file_path)
                filename = os.path.basename(temp_file_path)
                excel_data = {}
                for sheet_name in xls.sheet_names:
                    df = xls.parse(sheet_name)
                    df['文件名'] = filename
                    excel_data[sheet_name] = df.to_dict(orient='records')
                for df_name, df in excel_data.items():
                    updater.insert_one_df(pd.DataFrame(df), conf_dict)
                # os.remove(temp_file_path)
                finished_file_list.append(temp_file_path)
                # logger.info(f"Temporary file {temp_file_path} deleted successfully")
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('md'):
                file_info = read_file(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                result_list = process_markdown(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                # os.remove(temp_file_path)
                finished_file_list.append(temp_file_path)
                # logger.info(f"Temporary file {temp_file_path} deleted successfully")
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('pdf'):
                file_info = extract_pdf(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                result_list = process_txt(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                # os.remove(temp_file_path)
                finished_file_list.append(temp_file_path)
                # logger.info(f"Temporary file {temp_file_path} deleted successfully")
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('docx'):
                file_info = read_docx(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                result_list = process_docx(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                # os.remove(temp_file_path)
                finished_file_list.append(temp_file_path)
                # logger.info(f"Temporary file {temp_file_path} deleted successfully")
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('urls'):
                for url in urls:
                    file_info = read_url(url)
                    if file_info==[]:
                        logger.info(f"Failed to read file {temp_file_path}")
                        task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                        raise ValueError(f"Failed to read file {temp_file_path}")
                    result_list = process_url(file_info["file_content"], file_info["file_name"])
                    updater.insert_one_doc(result_list)
                    finished_file_list.append(temp_file_path)
                    task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
                    time.sleep(1.2)
            elif file_extension in ('txt'):
                file_info = read_txt(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                result_list = process_txt(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                # os.remove(temp_file_path)
                finished_file_list.append(temp_file_path)
                # logger.info(f"Temporary file {temp_file_path} deleted successfully")
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('zip'):
                extracted_path = unzip_file(temp_file_path)
                logger.info(f"extracted_path {extracted_path}")
                file_paths_list = list_files_in_folder(extracted_path)
                logger.info(f"file_paths_list {file_paths_list}")
                for file_path in file_paths_list:
                    single_file_extension = file_path.split('.')[-1].lower()
                    logger.info(f"single_file_extension {single_file_extension}")
                    file_info = read_file(file_path) if single_file_extension in ('md','txt') else extract_pdf(file_path) if single_file_extension == 'pdf' else read_docx(file_path) if single_file_extension == 'docx'else []
                    if file_info==[]:
                        logger.info(f"Failed to read file {file_path}")
                        continue
                    result_list = process_txt(file_info["file_content"], file_info["file_name"]) if single_file_extension in ('txt','pdf') else process_markdown(file_info["file_content"], file_info["file_name"]) if single_file_extension != 'docx' else process_docx(file_info["file_content"], file_info["file_name"])
                    updater.insert_one_doc(result_list)
                    # 需要增加多一点的时间给数据插入，随机休息8~10秒
                    snap = random.randint(18,30)
                    logger.info('sleeping for '+str(snap)+' seconds')
                    time.sleep(snap)
                    finished_file_list.append(file_info["file_name"])
                finished_file_list.append(temp_file_path)
                shutil.rmtree(extracted_path, ignore_errors=False, onerror=None)
                logger.info('finished insert files: '+','.join(finished_file_list))
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('article'):
                article_metadata = json.loads(article_metadata) if article_metadata else {}
                result_list = process_article(article_text, article_metadata)
                updater.insert_one_doc(result_list)
                finished_file_list.append(json.dumps(article_metadata))
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            else:
                task.update_state(state='FAILURE', meta={'exc_type': '','message': 'Unsupported file format'})
                raise ValueError('Unsupported file format')
        elif mode == 'qa_enhance':
            print('MODE: qa_enhance')
            if file_extension in ('md'):
                file_info = read_file(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                # 原来的模式也加上
                result_list = process_markdown(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('pdf'):
                file_info = extract_pdf(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                # 原来的模式也加上
                result_list = process_txt(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('docx'):
                file_info = read_docx(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                # 原来的模式也加上
                result_list = process_docx(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('urls'):
                for url in urls:
                    file_info = read_url(url)
                    logger.info(f"url {url}")
                    if file_info==[]:
                        logger.info(f"Failed to read file {url}")
                        task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {url}"})
                        raise ValueError(f"Failed to read file {url}")
                    text = file_info["file_content"]
                    filename = file_info["file_name"]
                    title = extract_md_title(text)
                    payload = get_qa_chunk(text,filename,title)
                    updater.insert_qa_doc(payload)
                    # 原来的模式也加上
                    result_list = process_url(file_info["file_content"], file_info["file_name"])
                    updater.insert_one_doc(result_list)
                    finished_file_list.append(temp_file_path)
                    task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('txt'):
                file_info = read_txt(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                # 原来的模式也加上
                result_list = process_txt(file_info["file_content"], file_info["file_name"])
                updater.insert_one_doc(result_list)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('zip'):
                extracted_path = unzip_file(temp_file_path)
                logger.info(f"extracted_path {extracted_path}")
                file_paths_list = list_files_in_folder(extracted_path)
                logger.info(f"file_paths_list {file_paths_list}")
                for file_path in file_paths_list:
                    single_file_extension = file_path.split('.')[-1].lower()
                    logger.info(f"single_file_extension {single_file_extension}")
                    file_info = read_file(file_path) if single_file_extension in ('md','txt') else extract_pdf(file_path) if single_file_extension == 'pdf' else read_docx(file_path) if single_file_extension == 'docx'else []
                    if file_info==[]:
                        logger.info(f"Failed to read file {file_path}")
                        continue
                    result_list = process_txt(file_info["file_content"], file_info["file_name"]) if single_file_extension in ('txt','pdf') else process_markdown(file_info["file_content"], file_info["file_name"]) if single_file_extension != 'docx' else process_docx(file_info["file_content"], file_info["file_name"])
                    updater.insert_one_doc(result_list)
                    finished_file_list.append(file_info["file_name"])
                    # QA增强模式
                    text = file_info["file_content"]
                    filename = file_info["file_name"]
                    title = extract_md_title(text)
                    payload = get_qa_chunk(text,filename,title)
                    updater.insert_qa_doc(payload)
                    # 需要增加多一点的时间给数据插入，随机休息8~10秒
                    snap = random.randint(18,30)
                    logger.info('sleeping for '+str(snap)+' seconds')
                    time.sleep(snap)
                finished_file_list.append(temp_file_path)
                logger.info('finished insert files: '+','.join(finished_file_list))
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            else:
                task.update_state(state='FAILURE', meta={'exc_type': '','message': 'Unsupported file format'})
                raise ValueError('Unsupported file format')
        elif mode == 'qa_only':
            print("mode is qa_only")
            if file_extension in ('md'):
                file_info = read_file(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('pdf'):
                file_info = extract_pdf(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('docx'):
                file_info = read_docx(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('urls'):
                for url in urls:
                    file_info = read_url(url)
                    if file_info==[]:
                        logger.info(f"Failed to read file {url}")
                        task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {url}"})
                        raise ValueError(f"Failed to read file {url}")
                    text = file_info["file_content"]
                    filename = file_info["file_name"]
                    title = extract_md_title(text)
                    payload = get_qa_chunk(text,filename,title)
                    updater.insert_qa_doc(payload)
                    finished_file_list.append(temp_file_path)
                    task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('txt'):
                file_info = read_txt(temp_file_path)
                if file_info==[]:
                    logger.info(f"Failed to read file {temp_file_path}")
                    task.update_state(state='FAILURE', meta={'exc_type': '','message': f"Failed to read file {temp_file_path}"})
                    raise ValueError(f"Failed to read file {temp_file_path}")
                text = file_info["file_content"]
                filename = file_info["file_name"]
                title = extract_md_title(text)
                payload = get_qa_chunk(text,filename,title)
                updater.insert_qa_doc(payload)
                finished_file_list.append(temp_file_path)
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            elif file_extension in ('zip'):
                extracted_path = unzip_file(temp_file_path)
                logger.info(f"extracted_path {extracted_path}")
                file_paths_list = list_files_in_folder(extracted_path)
                logger.info(f"file_paths_list {file_paths_list}")
                for file_path in file_paths_list:
                    single_file_extension = file_path.split('.')[-1].lower()
                    logger.info(f"single_file_extension {single_file_extension}")
                    file_info = read_file(file_path) if single_file_extension in ('md','txt') else extract_pdf(file_path) if single_file_extension == 'pdf' else read_docx(file_path) if single_file_extension == 'docx'else []
                    if file_info==[]:
                        logger.info(f"Failed to read file {file_path}")
                        continue                    
                    # QA增强模式
                    text = file_info["file_content"]
                    filename = file_info["file_name"]
                    title = extract_md_title(text)
                    payload = get_qa_chunk(text,filename,title)
                    updater.insert_qa_doc(payload)
                    # 需要增加多一点的时间给数据插入，随机休息8~10秒
                    snap = random.randint(58,90)
                    logger.info('sleeping for '+str(snap)+' seconds')
                    time.sleep(snap)
                    finished_file_list.append(file_info["file_name"])
                finished_file_list.append(temp_file_path)
                logger.info('finished insert files: '+','.join(finished_file_list))
                task.update_state(state='SUCCESS', meta={'message': 'Database update completed'})
            else:
                task.update_state(state='FAILURE', meta={'exc_type': '','message': 'Unsupported file format'})
                raise ValueError('Unsupported file format')
    except Exception as ex:
        exc_type = type(ex).__name__
        exc_message = traceback.format_exc().split('\n')
        logger.error(f"Error occurred: {exc_type} - {exc_message}")
        task.update_state(state='FAILURE', meta={'exc_type': exc_type, 'exc_message': exc_message})
        raise Ignore()
    finally:
        # Delete the temporary file and extracted folder if it's a ZIP file
        if os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.info(f"Temporary file {temp_file_path} deleted successfully")
                logger.info('finished insert files: '+','.join(finished_file_list))
                if file_extension == 'zip':
                    shutil.rmtree(extracted_path, ignore_errors=False, onerror=None)
                    logger.info(f"Extracted folder {extracted_path} deleted successfully")
                    
            except Exception as ex:
                exc_type = type(ex).__name__
                exc_message = traceback.format_exc().split('\n')
                logger.error(f"Failed to delete temporary file/folder: {ex}")
                task.update_state(state='FAILURE', meta={'exc_type': exc_type, 'exc_message': f"Failed to delete temporary file/folder: {ex}"+exc_message})
                raise Ignore()