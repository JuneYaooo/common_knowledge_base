import openai
import re
import json
from retrying import retry
import os
import time
import requests
def pulse_generate(prompt):
    url = "https://mchatgpt-internal.dev.6ccloud.com/v1/api/completion/generate_json"

    payload = json.dumps({
        "action": "To user",
        "parent_messages": [
            {
                "action": "From user",
                "content": prompt
            }
        ],
        "gen_kwargs": {
            "model": "102bv14_no_tools",
            "num_return_sequences": 1,
            "max_new_token":4096
        }
    })
    headers = {
        'accept': 'application/json',
        'Authorization': 'Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3NDJjYWM3Ny0wZWQ1LTQ3MjYtYmM1MS1lZjQ2Zjg5MjhkNWMiLCJleHAiOjIwMDYzOTUxNDQsInNjb3BlcyI6WyJ1c2VyIl19.CPuXznn-c4WHkYQU8bCMVyPr4tWwczDCdVDuzcPrWf4',
        'Content-Type': 'application/json'
    }

    response = requests.request("POST", url, headers=headers, data=payload)

    return response.json()['messages'][0]['content']['parts'][0]
# Define a custom wait strategy for retrying
def wait_exponential_multiplier():
    return 1000  # 1000 ms base wait time

def wait_exponential_max():
    return 10000  # 10000 ms max wait time

# Custom exception check function
def retry_on_any_exception(exception):
    print(f"An error occurred: {exception}")
    time.sleep(0.01)  # Wait for 0.01 seconds before retrying
    return True  # Always retry on any exception


def split_list_by_length(input_list, max_length):
    """将给定的字符串列表按照最大长度限制拆分成子列表"""
    current_list = []
    current_length = 0
    for item in input_list:
        if current_length + len(item) + 1 > max_length:  # +1 for newline character
            yield current_list
            current_list = [item]
            current_length = len(item)
        else:
            current_list.append(item)
            current_length += len(item) + 1
    if current_list:
        yield current_list


def process_input_list(input_list, max_length):
    """处理输入列表，按照最大长度限制拆分，但遇到表格时不中断"""
    text_list = []
    current_text = ""
    
    for line in input_list:
        if line.startswith('|'):
            # 如果是表格行，直接加到当前段落，不检查长度限制
            current_text += line + '\n'
        else:
            if len(current_text) + len(line) + 1 > max_length:
                text_list.append(current_text.strip())
                current_text = line + '\n'
            else:
                current_text += line + '\n'
    
    # 将最后一个段落添加到列表中
    if current_text:
        text_list.append(current_text.strip())
    
    return text_list

def check_keys(dictionary):
    required_keys = ['问题', '回答']
    
    # 检查所有必需的键是否都在字典中
    for key in required_keys:
        if key not in dictionary:
            return False
    
    # 如果所有必需的键都存在，则返回 True
    return True

# 根据编码列表筛选QA列表
def filter_qa_list(qa_list, code_list):
    filtered_list = []
    for item in qa_list:
        if isinstance(item, dict) and '编码' in item:
            if item['编码'] in code_list:
                filtered_list.append(item)
            else:
                print(f"错误: 编码 {item['编码']} 不在 code_list 范围内，已忽略。")
        else:
            print(f"错误: item 不是字典或缺少 '编码' 键，已忽略。")
    return filtered_list
  
def generate_qa_list_pulse(input_str, question_count, max_attempts=3):
    """
    尝试从通过get_input_str()获取的字符串中提取列表。
    如果没有找到匹配的列表，将重试，最多重试max_attempts次。

    参数:
    - get_input_str: 一个函数，当调用时返回一个新的输入字符串。
    - max_attempts: 允许的最大尝试次数，默认为3。

    返回:
    - 提取到的列表，或者在多次尝试后仍未找到时返回None。
    """
    attempt = 0
    while attempt < max_attempts:
        print('attempt',attempt)
        qa_extract_prompt = """\n帮我从上面的文档中总结出你认为大家可能会感兴趣的问题与回答，问题尽量口语化一点，回答尽量完整一点。不多于"""+str(question_count)+"""个问题回答对
按照json格式输出，每个list元素是一个字典，里面包含编号和问题回答。如
[
  {
    "编码":1,
    "问题": "XXX",
    "回答":"XXX"
  },
  {
    "编码":2,
    "问题": "XXX",
    "回答":"XXX"
  },
  ...
]"""
        llm_res = pulse_generate(input_str+qa_extract_prompt)
        print('generate_qa_list llm_res:\n',llm_res)
        # 使用正则表达式提取 JSON 部分
        match = re.search(r'\[.*?\]', llm_res, re.DOTALL)
        if match:
            json_str = match.group()
            try:
                # 使用 json.loads() 解析 JSON 字符串
                qa_list = json.loads(json_str)
                return qa_list
            except ValueError:
                # 如果转换失败（例如，格式不正确），继续尝试
                pass
            # 输出结果
            print(qa_list)
        attempt += 1
        print(f"尝试{attempt}: 没有找到匹配的列表")

    return None

def review_qa_list_qulse(qa_list, input_str):
    prompt = "请复核上面的[问题与回答列表]，确保它们合理且有意义。若问题和回答重复，回答冗长或无关，或者问题回答没有意义，请直接剔除，不需要重写。输出合理的编码列表。如[1, 3]，注意，列表里的数字需要和编码对应，不要返回不存在的编码"
    qa_content = json.dumps(qa_list, ensure_ascii=False)
    llm_res = pulse_generate('[原始参考内容]: ' + input_str + '\n[问题与回答列表]: ' + qa_content + "\n\n" + prompt)
    print('review_res', llm_res)
    match = re.search(r'\[.*?\]', llm_res, re.DOTALL)
    if match:
        try:
            code_list = json.loads(match.group())
            if all(isinstance(i, int) for i in code_list):
                return code_list
            else:
                print("错误: code_list 包含非整数值")
                return []
        except ValueError as e:
            print(f"JSON解析错误: {e}")
            print(f"匹配内容: {match.group()}")
            return []
    return []

# Pulse extract QA
def get_qa_chunk(text, filename, title, max_length=1000, question_count=5):
    try:
        parts = text.split('\n')  # 移除连续分隔符产生的空字符串
        parts = [part for part in parts if part]
        payload = []
        # 调用处理函数
        text_list = process_input_list(parts, max_length)
        for split_text in text_list:
            try:
                split_text = re.sub(r'!\[.*?\]\(.*?\)', '', split_text)
                if split_text.strip() == '':
                    continue
                print('split_text===\n',split_text)
                qa_list = generate_qa_list_pulse(split_text,question_count)
                if isinstance(qa_list, list) and all(isinstance(item, dict) for item in qa_list):
                    print("找到并提取了列表:", qa_list)
                    # 检查QA列表的合理性
                    code_list = review_qa_list_qulse(qa_list, split_text)
                    # 筛选出合理的QA列表
                    final_qa_list = filter_qa_list(qa_list, code_list)
                    print("复核后列表:", final_qa_list)
                    for qa_item in final_qa_list:
                        if check_keys(qa_item) == False:
                            continue
                        file_config = {'段落': split_text, '文件名': filename, '论文名': title}
                        value = qa_item.pop('编号', None)
                        payload.append({**qa_item, **file_config})
                else:
                    print("多次尝试后未能找到匹配的列表")
            except Exception as e:
                print(f"处理段落 '{split_text}' 时发生错误: {e}")
        return payload
    except Exception as e:
        print(f"处理文本时发生错误: {e}")
        return []