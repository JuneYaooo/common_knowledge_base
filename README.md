# common_knowledge_base
通用知识库

```
cd common_knowledge_base

docker compose build --no-cache

docker compose up

# 如果想取消
docker-compose down

# 删除无标签的内容
docker images -f "dangling=true" -q | xargs docker rmi
```