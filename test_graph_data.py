import sys
import json
from neo4j import GraphDatabase

driver = GraphDatabase.driver("neo4j://127.0.0.1:7687", auth=("neo4j", "123456789"))

with driver.session() as session:
    nodes = session.run("MATCH (n:Entity) RETURN n.id as id, n.name as name, n.type as type, n.description as desc, n.aliases as aliases").data()
    rels = session.run("MATCH (s:Entity)-[r]->(t:Entity) RETURN s.name as source, type(r) as type, t.name as target").data()
    print(f"Total entity nodes: {len(nodes)}")
    print(f"Total entity rels: {len(rels)}")
    print("Sample rels:")
    for r in rels[:15]:
        print(f"  {r['source']} -[{r['type']}]-> {r['target']}")

driver.close()
