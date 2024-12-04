from common.qdrant_new import VectorDatabaseUpdater
# rest_framework
from rest_framework.viewsets import ModelViewSet
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import action
import os
from rest_framework.decorators import action
from celery.result import AsyncResult
from .tasks import update_database_async
from django.conf import settings
from tqdm_joblib import tqdm_joblib
from joblib import Parallel, delayed
import traceback
from sentence_transformers import SentenceTransformer
import requests
from typing import List, Dict, Tuple
import ast
import time
import uuid

EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH")
QDRANT_HOST = os.getenv("QDRANT_HOST")
QDRANT_POST = os.getenv("QDRANT_POST")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME")

class CustomizeKBView(ModelViewSet):
    @action(detail=False, methods=['POST'])  # Use detail=False for list-level actions
    def recreate_kb(self, request):
        try:
            user_id = self.request.data.get('user_id')
            if user_id in settings.EMBEDDING_DB_MAPPING:
                if settings.EMBEDDING_DB_MAPPING[user_id]=='m3e-base':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.M3E_BASE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='e5-large':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.E5_LARGE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='bge-m3':
                    print('get_vector_search   bge-m3!!!')
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.BGE_M3_EMBEDDING_MODEL)
                else:
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            else:
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            # 清空并重新创建 collection
            updater.create_collection(user_id)
            response_data = {
                "message": "创建向量库成功",
                "data": {}
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'message': '创建向量库失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'])  # Use detail=False for list-level actions
    def delete_kb(self, request):
        try:
            user_id = self.request.data.get('user_id')
            updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                            user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            # 清空并重新创建 collection
            updater.clear_collection()
            response_data = {
                "message": "删除向量库成功",
                "data": {}
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'message': '删除向量库失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['POST'])
    def import_kb(self, request):
        try:
            user_id = self.request.data.get('user_id')
            conf_dict = self.request.data.get('conf_dict')
            mode = self.request.data.get('mode', 'normal')
            url = self.request.data.get('url', None)
            urls = self.request.data.get('urls', [])
            uploaded_file = self.request.FILES.get('file')
            article_text = self.request.data.get('article_text', None)
            article_metadata = self.request.data.get('article_metadata', {})

            if not uploaded_file and not url and not urls and not article_text:
                return Response({'message': '数据库更新失败', 'data': {'error': '文件未上传且未提供URL且未提供文章内容'}}, status=status.HTTP_400_BAD_REQUEST)
            if url and not urls:
                urls = [url]
            elif urls and not url:
                import ast
                try:
                    urls = ast.literal_eval(urls)
                except (ValueError, SyntaxError) as e:
                    return Response({'message': '数据库更新失败', 'data': {'errors': 'URLs解析失败: ' + str(e)}}, status=status.HTTP_400_BAD_REQUEST)
            local_file_path = ""
            if uploaded_file:
                file_extension = uploaded_file.name.split('.')[-1].lower()
                if file_extension not in ['xlsx', 'xls', 'md', 'zip', 'pdf', 'docx',"txt"]:
                    return Response({'message': '数据库更新失败', 'data': {'error': '文件格式不支持，目前只支持xlsx、xls、md、zip、pdf、docx、txt'}},
                                    status=status.HTTP_400_BAD_REQUEST)

                # 准备保存文件
                project_directory = os.getcwd()
                data_directory = os.path.join(project_directory, 'data', user_id)
                if not os.path.exists(data_directory):
                    os.makedirs(data_directory)
                
                local_file_path = os.path.join(data_directory, uploaded_file.name)

                # 分块写入文件
                with open(local_file_path, 'wb+') as local_file:
                    for chunk in uploaded_file.chunks():
                        local_file.write(chunk)

            task = update_database_async.apply_async(args=(user_id, conf_dict, local_file_path, mode, urls, article_text, article_metadata))

            response_data = {
                'message': '任务已提交',
                'data': {'task_id': task.id}
            }

            return Response(response_data, status=status.HTTP_202_ACCEPTED)
        except Exception as e:
            response_data = {
                'message': '数据库更新失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    
    @action(detail=False, methods=['POST'])
    def import_vectors(self, request):
        try:
            # 获取数据
            print('self.request.data~',self.request.data)
            user_id = self.request.data.get('user_id')
            payloads = self.request.data.get('payloads')
            texts = self.request.data.get('texts')

            # 校验 payloads 和 texts 是否为列表
            if not isinstance(payloads, list) or not isinstance(texts, list):
                raise ValueError('payloads 和 texts 必须都是列表。')

            # 校验 payloads 和 texts 长度是否一致
            if len(payloads) != len(texts):
                raise ValueError('payloads 和 texts 的长度不一致。')

            # 校验 payloads 列表中的每个元素是否为字典
            if not all(isinstance(item, dict) for item in payloads):
                raise ValueError('payloads 列表中的每个元素必须是字典。')

            # 校验 texts 列表中的每个元素是否为字符串
            if not all(isinstance(item, str) for item in texts):
                raise ValueError('texts 列表中的每个元素必须是字符串。')

            # 根据 payloads 长度生成对应数量的 UUID
            ids = [str(uuid.uuid4()) for _ in range(len(payloads))]

            # 更新向量数据库
            updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                            user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            update_res = updater.insert_data(ids, payloads, texts)

            # 返回成功响应
            response_data = {
                'message': '向量更新完成',
                'data': {'result': update_res}
            }
            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as ve:
            # 捕获并返回自定义的错误信息
            response_data = {
                'message': '向量更新失败',
                'data': {'errors': str(ve)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            # 捕获其他异常并返回错误信息
            response_data = {
                'message': '向量更新失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)

    # Endpoint to check task status
    @action(detail=False, methods=['GET'])
    def check_task_status(self, request):
        task_id = request.query_params.get('task_id')
        print('===task_id===', task_id)

        if not task_id:
            return Response({'message': 'Task ID not provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Retrieve task status from Redis using the task ID
        result = AsyncResult(task_id)
        print('===result===', str(result.result))

        if result.state == 'PENDING':
            return Response({'message': 'Task not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            task_status = {
                'task_id': task_id,
                'status': result.state,
                'result': result.result,
            }
            return Response(task_status, status=status.HTTP_200_OK)
        except TypeError as e:
            return Response({'message': f'Error serializing result: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    
    @action(detail=False, methods=['POST'])  # Use detail=False for list-level actions
    def get_vector_search(self, request):
        blocked_ips = []
        # 检查请求的IP地址是否被禁止
        client_ip = request.META.get('REMOTE_ADDR')
        print('client_ip',client_ip)
        if client_ip in blocked_ips:
            response_data = {
                'message': '访问被禁止',
                'data': {'errors': '您的IP地址已被禁止访问'}
            }
            return Response(response_data, status=status.HTTP_403_FORBIDDEN)
        try:
            start_time = time.time()
            print('self.request.data~',self.request.data)
            user_id = self.request.data.get('user_id')
            query = self.request.data.get('query')
            top_k = self.request.data.get('top_k')
            # print('top_k',top_k)
            threshold = self.request.data.get('threshold')
            cond_key = self.request.data.get('cond_key', None) 
            cond_value = self.request.data.get('cond_value', None)
            sort_rules = self.request.data.get('sort_rules', [])
            # updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
            #                                 user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            
            if user_id in settings.EMBEDDING_DB_MAPPING:
                if settings.EMBEDDING_DB_MAPPING[user_id]=='m3e-base':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.M3E_BASE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='e5-large':
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.E5_LARGE_EMBEDDING_MODEL)
                elif settings.EMBEDDING_DB_MAPPING[user_id]=='bge-m3':
                    print('get_vector_search   bge-m3!!!')
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                            user_id, embedding_model=settings.BGE_M3_EMBEDDING_MODEL)
                else:
                    updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            else:
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
            
            if cond_key and cond_value:
                data = updater.query_collection_condition(query, limit=10000, score_threshold=threshold, key=cond_key, value=cond_value)
            else:
                data = updater.query_collection(query, limit=10000, score_threshold=threshold)
            final_results = []
            count = 1
            payload_unique_dict = {}
            # 如果有排序规则
            parsed_sort_rules = parse_sort_rules(sort_rules) if sort_rules!= [] else sort_rules
            print('parsed_sort_rules',parsed_sort_rules)
            if len(parsed_sort_rules)>0:
                data = sort_scored_points(data, parsed_sort_rules)
            print('top_k',top_k)
            print('count',count)
            
            for values in data:
                if count > top_k:
                    break
                item_dict = {}
                metadata = values.payload  # Assuming values.payload contains the metadata
                
                # Constructing markdown titles
                markdown_titles = ""
                if metadata.get('title_level1'):
                    markdown_titles += f"# {metadata['title_level1']}\n"
                    metadata.pop('title_level1', None)
                if metadata.get('title_level2'):
                    markdown_titles += f"## {metadata['title_level2']}\n"
                    metadata.pop('title_level2', None)
                if metadata.get('title_level3'):
                    markdown_titles += f"### {metadata['title_level3']}\n"
                    metadata.pop('title_level3', None)
                if metadata.get('段落'):
                    # Combine titles and paragraph
                    combined_paragraph = f"{markdown_titles}{metadata['段落']}"
                    # Remove title levels from metadata
                
                item_dict['metadata'] = metadata
                if metadata.get('段落'):
                    item_dict['metadata']['段落'] = combined_paragraph  # Update paragraph with markdown titles
                
                if str(item_dict['metadata']) in payload_unique_dict:
                    continue
                else:
                    payload_unique_dict[str(item_dict['metadata'])] = 1
                
                item_dict['score'] = values.score  # Assuming values.score contains the score
                final_results.append(item_dict)
                count += 1

            # 保持格式统一
            mapping_dict = {key: key for key, value in item_dict['metadata'].items()} if len(final_results)>0 else {}
            end_time = time.time()
            cost_time = end_time - start_time
            print(f'query: {query} user_id: {user_id}\ncost_time: {round(cost_time,3)} seconds')
            response_data = {
                "message": "向量搜索成功",
                "data": final_results,
                "mapping": mapping_dict
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'message': '向量搜索失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)


    @action(detail=False, methods=['POST'])  # Use detail=False for list-level actions
    def get_merged_vector_search(self, request):
        try:
            user_ids = self.request.data.get('user_ids', [])
            if not isinstance(user_ids, list):
                raise ValueError('user_ids必须为列表格式')
            query = self.request.data.get('query')
            top_k = self.request.data.get('top_k')
            threshold = self.request.data.get('threshold')
            num_worker = min(4, len(user_ids))
            try:
                with tqdm_joblib(desc="Coarse Select", total=len(user_ids)) as progress_bar:
                    coarse_vector_list = Parallel(n_jobs=num_worker)([delayed(get_unique_vectors)(user_id,query,threshold,top_k) for user_id in user_ids])
            except Exception as e:
                print('error!!',e)
                traceback.print_exc()
            # flattened_list = [element for sublist in coarse_vector_list for element in sublist]
            flattened_list = [item2 for item1, item2 in coarse_vector_list if item1 for item2 in item1]
            mapping_dict = {}
            for item in coarse_vector_list:
                mapping_dict.update(item[1])
            flattened_list = deduplicate_list_by_metadata(flattened_list)
            sorted_vector_list = sorted(flattened_list, key=lambda x: x["score"], reverse=True)
            # 保持格式统一
            # mapping_dict = {key: key for key, value in sorted_vector_list[0].items()} if len(sorted_vector_list)>0 else {}
            response_data = {
                "message": "向量搜索成功",
                "data": sorted_vector_list[:top_k],
                "mapping": mapping_dict
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except Exception as e:
            response_data = {
                'message': '向量搜索失败',
                'data': {'errors': str(e)}
            }
            return Response(response_data, status=status.HTTP_400_BAD_REQUEST)


def get_unique_vectors(user_id,query,threshold,top_k):
    try:
        # 判断embedding 是否有配对，没有的话就用默认的
        if user_id in settings.EMBEDDING_DB_MAPPING:
            if settings.EMBEDDING_DB_MAPPING[user_id]=='m3e-base':
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                        user_id, embedding_model=settings.M3E_BASE_EMBEDDING_MODEL)
            elif settings.EMBEDDING_DB_MAPPING[user_id]=='e5-large':
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                        user_id, embedding_model=settings.E5_LARGE_EMBEDDING_MODEL)
            elif settings.EMBEDDING_DB_MAPPING[user_id]=='bge-m3':
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                                        user_id, embedding_model=settings.BGE_M3_EMBEDDING_MODEL) 
            else:
                updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
        else:
            updater = VectorDatabaseUpdater(EMBEDDING_MODEL_PATH, QDRANT_HOST, QDRANT_POST,
                                        user_id, embedding_model=settings.MY_GLOBAL_EMBEDDING_MODEL)
        
        data = updater.query_collection(query, limit=10000, score_threshold=threshold)
        final_results = []
        count = 1
        payload_unique_dict = {}
        for values in data:
            if count > top_k:
                break
            item_dict = {}
            item_dict['metadata'] = values.payload
            if str(item_dict['metadata']) in payload_unique_dict:
                continue
            else:
                payload_unique_dict[str(item_dict['metadata'])]=1
            item_dict['score'] = values.score
            item_dict['db_source'] = user_id
            final_results.append(item_dict)
            count += 1
        mapping_dict = {key: key for key, value in item_dict['metadata'].items()} if len(final_results)>0 else {}
        return final_results,mapping_dict
    except Exception as e:
        print(f"An error occurred: {e}")
        # You can raise the exception again if needed or handle it accordingly
        # raise e
        return [],{}
    
def deduplicate_list_by_metadata(input_list):
    seen_metadata = set()
    unique_list = []

    for item in input_list:
        metadata_str = str(item.get('metadata', {}))
        if metadata_str not in seen_metadata:
            seen_metadata.add(metadata_str)
            unique_list.append(item)

    return unique_list

class ScoredPoint:
    def __init__(self, id, version, score, payload, vector=None):
        self.id = id
        self.version = version
        self.score = score
        self.payload = payload
        self.vector = vector

    def __repr__(self):
        return f"ScoredPoint(id={self.id}, version={self.version}, score={self.score}, payload={self.payload})"

def sort_scored_points(points: List[ScoredPoint], sort_rules: List[Tuple[str, str]]) -> List[ScoredPoint]:
    print('sort_scored_points sort_rules',sort_rules[0])
    for field, order in reversed(sort_rules):  # Reversed to apply the last rule first
        print('field, order',field, order)
        reverse = True if order.lower() == 'desc' else False
        print('reverse',reverse)
        # print('points',points)
        # points.sort(key=lambda x: x.payload.get(field), reverse=reverse)
        points.sort(key=lambda x: (isinstance(x.payload.get(field), str), x.payload.get(field) if isinstance(x.payload.get(field), (int, float)) else float('inf')), reverse=reverse)
        print('sort points',points,'sort points')
    return points

def parse_sort_rules(sort_rules_str: str):
    try:
        # 去除字符串的首尾空格，确保没有额外的空白字符
        sort_rules_str = sort_rules_str.strip()
        
        # 使用 ast.literal_eval 解析字符串为 Python 对象
        sort_rules = ast.literal_eval(sort_rules_str)
        
        # 检查解析结果是否为列表
        if isinstance(sort_rules, list):
            return sort_rules
        else:
            raise ValueError("The parsed object is not a list")
    except (ValueError, SyntaxError) as e:
        print(f"Error parsing sort rules: {e}")
        return []
