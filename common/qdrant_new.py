from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.models import CollectionStatus
import time
import sys
import os
import random  # 导入 random 模块
import shutil
import requests
from itertools import permutations
import uuid

def generate_uuid():
    """
    生成一个不包含短划线的UUID字符串。
    
    Returns:
        str: 不包含短划线的UUID字符串。
    """
    # 生成 UUID
    generated_uuid = uuid.uuid4()
    
    # 将 UUID 转换为字符串并去掉中间的短划线
    uuid_without_dashes = str(generated_uuid).replace('-', '')
    
    return uuid_without_dashes

class VectorDatabaseUpdater:
    def __init__(self, model_path, qdrant_host, qdrant_port, collection_name, embedding_model=None, batch_size=os.getenv("INSERT_BATCH_SIZE"), device=os.getenv('DEVICE')):
        # print('embedding_model',embedding_model)
        self.embedding_model = SentenceTransformer(model_path, device=device) if embedding_model is None else embedding_model
        self.embedding_size = self.embedding_model.get_sentence_embedding_dimension()
        # print('self.embedding_size',self.embedding_size)
        directory_name = os.path.basename(model_path)
        self.model_name = 'e5' if 'e5' in directory_name else 'm3e' if 'm3e' in directory_name else ''
        self.qdrant_host = qdrant_host
        self.qdrant_port = qdrant_port
        self.collection_name = collection_name
        self.batch_size = int(batch_size)
        self._connect_to_qdrant()  # 连接到Qdrant服务

    def _connect_to_qdrant(self):
        self.qdrant_client = QdrantClient(host=self.qdrant_host, port=self.qdrant_port, timeout=100)

    def get_collection_info(self):
        collection_info = self.qdrant_client.get_collection(collection_name=self.collection_name)
        return collection_info

    def clear_collection(self):
        """
        清空向量数据库中的集合。
        """
        self.qdrant_client.delete_collection(self.collection_name)

    def create_collection(self, new_collection_name):
        """
        删除现有的集合（如果存在），然后创建一个新的集合。

        参数：
        - new_collection_name: 新的集合名称
        """
        # 删除现有的集合（如果存在）
        self.qdrant_client.delete_collection(self.collection_name)

        # 创建新的集合
        self.collection_name = new_collection_name
        self.qdrant_client.create_collection(collection_name=self.collection_name,
                                             vectors_config=models.VectorParams(size=self.embedding_size,
                                                                                distance=models.Distance.COSINE),
                                            optimizers_config={"default_segment_number": 2})

    def wait_for_green_status(self, max_attempts=30):
        attempt_count = 0  # 初始化尝试次数

        while True:
            try:
                collection_info = self.get_collection_info()
                if collection_info.status == CollectionStatus.GREEN:
                    return True

                print('Status is not GREEN, retrying...', collection_info.status)
            except Exception as e:
                print(f"Failed to get collection info: {e}")

            attempt_count += 1

            if attempt_count > max_attempts:
                print('Max attempts reached, terminating...')
                return False

            if attempt_count <= 10:  # 尝试次数在1到10之间
                sleep_time = random.randint(3, 10)  # 生成1到6之间的随机数
            elif attempt_count <= 20:  # 尝试次数在11到20之间
                sleep_time = random.randint(10, 15)  # 生成5到10之间的随机数
            else:  # 尝试次数在21到30之间
                sleep_time = random.randint(15, 30)  # 生成10到15之间的随机数

            print(f'Sleeping for {sleep_time} seconds...')
            time.sleep(sleep_time)

            # 重新连接到qdrant
            self.reconnect_to_qdrant()

    def insert_data(self, ids, payloads, texts):
        start_time = time.time()

        for i in range(0, len(ids), self.batch_size):
            batch_ids = ids[i:i + self.batch_size]
            batch_payloads = payloads[i:i + self.batch_size]
            batch_text = texts[i:i + self.batch_size]

            batch_vectors = self.embedding_model.encode(batch_text).tolist()
            vectors_data = batch_ids + batch_payloads + batch_vectors
            vectors_size_bytes = sys.getsizeof(vectors_data)
            vectors_size_megabytes = vectors_size_bytes / (1024 * 1024)

            # 插入前先判断
            if not self.wait_for_green_status():
                raise Exception("等待绿色状态超时，程序中断")

            retries = 0
            success = False
            while retries < 5:
                try:
                    self.qdrant_client.upsert(
                        collection_name=self.collection_name,
                        points=models.Batch(
                            ids=batch_ids,
                            payloads=batch_payloads,
                            vectors=batch_vectors
                        ),
                    )
                    success = True
                    break  # 如果成功就跳出重试循环
                except requests.exceptions.RequestException as e:
                    if "timeout" in str(e) or "timed out" in str(e) or 'Timeout' in str(e):
                        retries += 1
                        print(f"重试 {retries} 次...")
                    else:
                        print(f"发生请求异常: {e}")
                        break  # 如果不是 timeout 错误，就不再重试
                except Exception as ex:
                        retries += 1
                        import traceback
                        exc_type = type(ex).__name__
                        exc_message = traceback.format_exc().split('\n')
                        print(f"Error occurred: {exc_type} - {exc_message}")
                        self.reconnect_to_qdrant()
                        if not self.wait_for_green_status():
                            raise Exception("等待绿色状态超时，程序中断")

            if not success:
                print("重试5次仍然失败，程序中断")
                break  # 如果多次重试失败，退出循环

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"insert {len(ids)} data, Time spent: {elapsed_time:.5f} seconds")

    def reconnect_to_qdrant(self, new_host=None, new_port=None, new_collection_name=None):
        """
        重新连接到Qdrant服务，可以指定新的主机、端口和表名。最多重试5次，每次失败后休息1到2秒。

        参数：
        - new_host: 新的Qdrant主机
        - new_port: 新的Qdrant端口
        - new_collection_name: 新的表名
        """
        retries = 0

        while retries < 5:
            try:
                self.qdrant_host = new_host if new_host else self.qdrant_host
                self.qdrant_port = new_port if new_port else self.qdrant_port
                self.collection_name = new_collection_name if new_collection_name else self.collection_name
                self._connect_to_qdrant()  # 重新连接到Qdrant服务
                return  # 连接成功，退出循环
            except Exception as e:
                print(f"Failed to reconnect to Qdrant: {e}")
                retries += 1
                if retries < 5:
                    # 休息1到2秒
                    sleep_time = 2 + random.random()  # 生成1到2之间的随机小数
                    print(f"Sleeping for {sleep_time:.2f} seconds...")
                    time.sleep(sleep_time)

        raise Exception("重连5次仍然失败，程序中断")

    def query_collection(self, query, limit=30, score_threshold=0.7, max_retries=5):
        retry_count = 0
        res = []
        
        while retry_count < max_retries and not res:
            print(f'start query (attempt {retry_count + 1}): {query}')
            start_time = time.time()
            
            if self.model_name == 'e5':
                query += 'query: '
            
            query_embed = self.embedding_model.encode([query]).tolist()[0]
            res = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_embed,
                limit=limit,
                score_threshold=score_threshold
            )
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            # print(f"Time spent: {elapsed_time:.5f} seconds")
            # print('res',query,self.collection_name, res)
            
            retry_count += 1
        
        return res

    def query_collection_condition(self, query, limit=30, score_threshold=0.7, key="level",value="资料"):
        start_time = time.time()
        if self.model_name == 'e5':
            query += 'query: '
        query_embed = self.embedding_model.encode([query])[0]
        res = self.qdrant_client.search(
            collection_name=self.collection_name,
            query_vector=query_embed,
            query_filter=models.Filter(
                must=[models.FieldCondition(key=key, match=models.MatchValue(value=value))]),
            limit=limit,
            score_threshold=score_threshold
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Time spent: {elapsed_time:.5f} seconds")
        return res

    def delete_points_condition(self, key="level", value="资料"):
        start_time = time.time()
        res = self.qdrant_client.delete(
            collection_name=self.collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value),
                        ),
                    ],
                )
            ),
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Delete successfully， Time spent: {elapsed_time:.5f} seconds")
        return res

    def insert_one_df(self, df, conf_dict={}):
        print('conf_dict~~',conf_dict)
        ids, texts, payloads = [], [], []
        undup_df = df.drop_duplicates()
        vectors_count = self.get_collection_info().vectors_count
        swapped_conf_dict = {value: key for key, value in conf_dict.items()}
        keys_with_global_prefix = [key for key, value in conf_dict.items() if value == '全局前缀']
        print('keys_with_global_prefix',keys_with_global_prefix)
        for i, row in undup_df.iterrows():
            for col in undup_df.columns:
                if col in conf_dict and (conf_dict[col] == '仅展示' or conf_dict[col] == '全局前缀'):
                    continue
                if row[col] is None or row[col] == '' or row[col] == '-' or row[col] == '无':
                    continue

                if col in conf_dict and '换行符拆解' in conf_dict[col]:
                    texts_list = row[col].split('\n')
                    for j, text in enumerate(texts_list):
                        if len(keys_with_global_prefix)>0:
                            for k, global_prefix in enumerate(keys_with_global_prefix):
                                print('k, global_prefix',k, global_prefix, row[global_prefix])
                                embed_text = str(row[global_prefix]) +' ' + str(col) + ' ' + str(text) if col in conf_dict and '带标题' in conf_dict[col] else str(row[global_prefix]) +' ' + str(text)
                                embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                                texts.append(embed_text)
                                payload = row.to_dict()
                                payloads.append(payload)
                                cur_uuid = generate_uuid()
                                ids.append(cur_uuid)
                        else:
                            embed_text = str(col) + ' ' + str(text) if col in conf_dict and '带标题' in conf_dict[col] else str(text)
                            embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                            texts.append(embed_text)
                            payload = row.to_dict()
                            payloads.append(payload)
                            cur_uuid = generate_uuid()
                            ids.append(cur_uuid)
                elif col in conf_dict and '排列组合' in conf_dict[col]:
                    texts_list = row[col].split('|')
                    # 获取所有可能的顺序组合
                    all_permutations = permutations(texts_list)
                    print('all_permutations',all_permutations)
                    
                    # 遍历所有组合并打印结果
                    i=0
                    for perm in all_permutations:
                        new_text = '|'.join(perm)
                        if len(keys_with_global_prefix)>0:
                            for k, global_prefix in enumerate(keys_with_global_prefix):
                                print('k, global_prefix',k, global_prefix, row[global_prefix])
                                embed_text = str(row[global_prefix]) +' ' + str(col) + ' ' + str(new_text) if col in conf_dict and '带标题' in conf_dict[col] else str(row[global_prefix]) +' ' + str(new_text)
                                embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                                texts.append(embed_text)
                                payload = row.to_dict()
                                payloads.append(payload)
                                cur_uuid = generate_uuid()
                                ids.append(cur_uuid)
                        else:
                            embed_text = str(col) + ' ' + str(new_text) if col in conf_dict and '带标题' in conf_dict[col] else str(new_text)
                            embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                            texts.append(embed_text)
                            payload = row.to_dict()
                            payloads.append(payload)
                            cur_uuid = generate_uuid()
                            ids.append(cur_uuid)
                else:
                    if len(keys_with_global_prefix)>0:
                        for k, global_prefix in enumerate(keys_with_global_prefix):
                                if row[global_prefix] is None or row[global_prefix] == '' or row[global_prefix] == '-' or row[global_prefix] == '无':
                                    continue
                                print('k, global_prefix',k, global_prefix, row[global_prefix])
                                embed_text = str(row[global_prefix]) +' ' + str(col) + ' ' + str(row[col]) if col in conf_dict and '带标题' in conf_dict[col] else str(row[global_prefix]) +' ' + str(row[col])
                                embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                                texts.append(embed_text)
                                payload = row.to_dict()
                                payloads.append(payload)
                                cur_uuid = generate_uuid()
                                ids.append(cur_uuid)
                    else:
                        embed_text = str(col) + ' ' + str(row[col]) if col in conf_dict and '带标题' in conf_dict[col] else str(row[col])
                        embed_text = 'passage: ' + embed_text if self.model_name =='e5' else embed_text
                        texts.append(embed_text)
                        payload = row.to_dict()
                        payloads.append(payload)
                        cur_uuid = generate_uuid()
                        ids.append(cur_uuid)
            # print('ids',ids)
            # print('payloads',payloads)
            # print('texts',texts)
        self.insert_data(ids, payloads, texts)


    def insert_one_doc(self, doc_list=[]):
            ids, texts, payloads = [], [], []
            vectors_count = self.get_collection_info().vectors_count
            for i, row in enumerate(doc_list):
                if 'text' not in row:
                    continue
                embed_text = 'passage: ' + row['text'] if self.model_name =='e5' else row['text']
                texts.append(embed_text)
                payload = row
                # 删除键为 'text' 的键值对
                if 'text' in payload:
                    payload.pop('text')
                payloads.append(payload)
                cur_uuid = generate_uuid()
                ids.append(cur_uuid)
            self.insert_data(ids, payloads, texts)

    def insert_qa_doc(self, doc_list=[]):
            ids, texts, payloads = [], [], []
            vectors_count = self.get_collection_info().vectors_count
            print('=====vectors_count=====',vectors_count)
            k=1
            for i, row in enumerate(doc_list):
                print('=======doc_list=======',doc_list)
                #  QA
                if '问题' not in row:
                    continue
                embed_text = 'passage: ' + row['问题'] if self.model_name =='e5' else row['问题']
                texts.append(embed_text)
                payloads.append(row)
                cur_uuid = generate_uuid()
                ids.append(cur_uuid)
                k+=1
            print('ids',ids)
            self.insert_data(ids, payloads, texts)