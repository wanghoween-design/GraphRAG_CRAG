from neo4j import GraphDatabase

from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

class GraphQueryService:
    """通过图谱查找人物的关系以及地点等。"""
    def __init__(self, uri, username, password):
        self.driver = GraphDatabase.driver(uri, auth=(username, password))

    def close(self):
        self.driver.close()

    def query_graph_context(self, person_name: str):
        """查找角色的母亲、保护者以及相关地点。

        Neo4j 离线或查询失败时返回空列表并告警, 保证 CRAG 流程可以
        继续依赖向量检索路径, 而不是整条管线抛异常中断。
        """
        results = []

        try:
            with self.driver.session() as session:

                #查询母亲关系
                mother_query = """
                MATCH (child:Entity {name:$name})<-[:MOTHER_OF]-(mother:Entity)
                RETURN (mother.name) AS value
                """
                mother_result = session.run(mother_query, name = person_name).single()
                if mother_result:
                    results.append(f"{person_name}的母亲是{mother_result['value']}")

                #查询保护关系
                protector_query = """
                MATCH (target:Entity {name: $name})<-[:PROTECTS]-(protector:Entity)
                RETURN protector.name AS value
"""
                protector_result = session.run(protector_query, name = person_name).single()
                if protector_result:
                    results.append(f"保护{person_name}的是{protector_result['value']}")

                #查询地点
                place_query = """
                MATCH (person:Entity {name: $name})-[:LOCATED_IN]->(place:Entity)
                RETURN collect(place.name) AS values
                """
                place_result = session.run(place_query, name = person_name).single()
                if place_result and place_result["values"]:
                    places = "、".join(place_result["values"])
                    results.append(f"与{person_name}相关的地点包括:{places}")
        except Exception as e:
            print(f"  [GraphService] Neo4j 图谱查询失败({person_name}): {e}")

        return results
