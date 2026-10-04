# -*- coding: utf-8 -*-
"""
CRAG (Corrective Retrieval-Augmented Generation) Service for the Web App.

双引擎架构:
1. LangGraphCRAGEngine — 真正的 Retrieve-Grade-Recover LangGraph 闭环管线
   (Ollama qwen3:4b 推理 + Neo4j 图谱检索 + FAISS 向量检索 + bge 精排 + Tavily 联网兜底),
   由 MemorySaver checkpointer 按 session_id 提供多轮对话记忆。
   Ollama 可达时自动启用; 构建或调用失败时自动降级。
2. RuleBasedCRAGEngine — 离线兜底引擎: 本地图谱三元组匹配 +
   全书 719 章全语料关键词检索, 引用全部来自真实命中章节。

对外统一由 WebCRAGService.query() 分发, 返回结构与前端 CRAG 推演卡片契约一致。
"""
import os
import re
import json
import socket
import threading
from typing import Dict, List, Any, Optional

from graph_data_provider import graph_provider, CHARACTER_LORE, SUPPLEMENTARY_LORE
from config import LLM_NAME


def is_ollama_active(host: str = "127.0.0.1", port: int = 11434, timeout: float = 0.5) -> bool:
    """快速探测本地 Ollama 服务是否就绪"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def clean_think(text: str) -> str:
    """剔除思考型模型输出中的 <think>...</think> 段落"""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


# ============================================================
# 全书章节检索器: 719 章全语料, 真实章节引用
# ============================================================

class ChapterRetriever:
    """
    全书章节关键词检索。
    覆盖 chapters.json 全部 719 章 (标题强加权 + 正文词频),
    只返回真实命中的章节 —— 杜绝"编造引用"。
    """
    def __init__(self):
        self.chapters: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        ch_path = os.path.join(os.path.dirname(__file__), "data", "processed", "chapters.json")
        try:
            with open(ch_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.chapters = [
                {
                    "volume": c.get("volume", ""),
                    "chapter_title": c.get("chapter_title", ""),
                    "chapter_index": c.get("chapter_index", 0),
                    "content": c.get("content", "")
                }
                for c in data
            ]
            print(f"[CRAG] 章节语料加载完成: 全书 {len(self.chapters)} 章")
        except Exception as e:
            print(f"[CRAG] Chapters index load error: {e}")

    def search(self, entities: List[str], question: str = "", top_k: int = 3) -> List[Dict[str, Any]]:
        """按实体在标题/正文的命中打分, 返回 top_k 条真实命中章节

        - 实体: 标题强加权 + 正文词频
        - 问题关键词切片 (如"杀手之王"/"大东山"): 仅参与标题匹配, 补充非实体线索
        """
        if not entities and not question:
            return []
        # 问题切片: 长度 3-8 的汉字片段 (排除"是谁"等2字泛词), 用于标题线索匹配
        q_terms = set()
        if question:
            for seg_len in range(3, 9):
                for s in range(0, max(0, len(question) - seg_len + 1)):
                    seg = question[s:s + seg_len]
                    if re.fullmatch(r"[\u4e00-\u9fff]{3,8}", seg):
                        q_terms.add(seg)
        scored = []
        for ch in self.chapters:
            title = ch["chapter_title"]
            content = ch["content"]
            score = 0
            first_pos = -1
            for ent in entities:
                if ent in title:
                    score += 12
                cnt = content.count(ent)
                if cnt:
                    score += min(cnt, 8) * 2
                    if first_pos < 0:
                        first_pos = content.find(ent)
            for term in q_terms:
                if term in title:
                    score += 6
            if score > 0:
                if first_pos >= 0:
                    start = max(0, first_pos - 40)
                    snippet = content[start:first_pos + 160].strip()
                else:
                    snippet = content[:160].strip()
                scored.append({
                    "volume": ch["volume"],
                    "chapter_title": ch["chapter_title"],
                    "chapter_index": ch["chapter_index"],
                    "score": score,
                    "snippet": snippet
                })
        scored.sort(key=lambda x: -x["score"])
        return scored[:top_k]

    def format_citations(self, matched: List[Dict[str, Any]]) -> List[str]:
        return [f"《庆余年》{m['volume']} · {m['chapter_title']}" for m in matched]


# 模块级共享单例 (章节语料全量驻留内存, 只加载一次)
chapter_retriever = ChapterRetriever()


# ============================================================
# 引擎一: 离线规则兜底 (Ollama/Neo4j 均离线时可用)
# ============================================================

def _extract_entities(text: str) -> List[str]:
    """识别提问中的小说人物与势力实体"""
    candidates = [
        "范闲", "叶轻眉", "庆帝", "五竹", "陈萍萍", "范建", "林婉儿", "范若若",
        "范思辙", "费介", "长公主", "李云睿", "太子", "二皇子", "苦荷", "四顾剑",
        "叶流云", "海棠朵朵", "王启年", "藤子京", "司理理", "皇太后", "老夫人",
        "林若甫", "监察院", "内库", "黑骑", "户部", "靖郡王", "京都", "澹州",
        "北齐", "东夷城", "神庙", "肖恩", "战豆豆", "庄墨韩"
    ]
    found = []
    alias_map = {
        "范慎": "范闲", "小范大人": "范闲", "安之": "范闲",
        "小叶子": "叶轻眉", "老妈": "叶轻眉",
        "皇帝": "庆帝", "陛下": "庆帝",
        "瞎子": "五竹", "黑布叔": "五竹",
        "陈院长": "陈萍萍", "老瘸子": "陈萍萍",
        "鸡腿姑娘": "林婉儿", "晨郡主": "林婉儿", "晨儿": "林婉儿",
        "李云睿": "长公主", "老二": "二皇子",
        "滕梓荆": "藤子京", "财政部": "户部",
    }
    for alias, real in alias_map.items():
        if alias in text and real not in found:
            found.append(real)
    for c in candidates:
        if c in text and c not in found:
            found.append(c)
    if not found and ("身世" in text or "主角" in text or "关系" in text):
        found.append("范闲")
    return found


class RuleBasedCRAGEngine:
    """
    离线兜底 CRAG: 图谱三元组 + 全书章节检索 + 规则模板合成。
    引用全部来自真实命中的章节, 检索不到时如实说明。
    """

    def query(self, question: str, session_id: str = "default_session") -> Dict[str, Any]:
        q = question.strip()
        entities = _extract_entities(q)

        # 1. Memory Node
        memory_trace = {
            "node": "Memory Node (指代消解与记忆召回)",
            "status": "success",
            "detected_entities": entities,
            "standalone_question": q,
            "description": f"已识别核心小说实体: {'、'.join(entities) if entities else '泛化剧情(离线规则引擎)'}"
        }

        # 2. Graph Retrieval: 本地图谱三元组召回
        graph_triples = []
        full_graph = graph_provider.get_full_graph()
        for ent in entities:
            for l in full_graph["links"]:
                if l["source"] == ent or l["target"] == ent:
                    triple_str = f"【{l['source']}】 ──[{l['label']}]──> 【{l['target']}】"
                    evidence = l.get("evidence", "")
                    if evidence:
                        triple_str += f" (原著依据: {evidence})"
                    if triple_str not in graph_triples:
                        graph_triples.append(triple_str)

        # 3. Chapter Retrieval: 全书 719 章真实命中
        matched = chapter_retriever.search(entities, question=q, top_k=3)
        matched_chapters = chapter_retriever.format_citations(matched)

        # 4. Grader Node: 证据充分度评估 (规则启发式)
        is_sufficient = bool(graph_triples or matched)
        if len(graph_triples) >= 2 and matched:
            confidence = 0.85
        elif graph_triples or matched:
            confidence = 0.7
        else:
            confidence = 0.35
        grader_trace = {
            "node": "Grader Node (CRAG 质量评估器)",
            "is_sufficient": is_sufficient,
            "confidence_score": confidence,
            "status": "PASS" if is_sufficient else "REWRITE",
            "reasoning": (
                f"离线引擎: 图谱命中 {len(graph_triples)} 条三元组, "
                f"全书语料真实命中 {len(matched)} 章。"
                + ("" if is_sufficient else " 未检索到有效证据, 建议补充人物名后重试。")
            ),
            "missing_info": None if is_sufficient else "缺少精准人物定位, 建议细化人名提问"
        }

        # 5. Rewrite 建议 (仅提示, 不实际触发联网)
        rewrite_trace = None
        if not is_sufficient:
            rewrite_trace = {
                "node": "Rewrite Node (提问自动优化)",
                "rewritten_question": f"《庆余年》中与「{entities[0] if entities else '主要人物'}」相关的人物关系与原著情节？",
                "trigger_web_search": False
            }

        # 6. Generate Node (事实型快答优先, 未命中再走考据模板)
        final_answer = (
            self._try_factoid_answer(q, entities, full_graph, matched)
            or self._generate_answer(q, entities, graph_triples, matched)
        )

        steps = [memory_trace,
                 {
                     "node": "Retrieve Node (Neo4j 图谱三元组召回)",
                     "triples": graph_triples[:6],
                     "total_triples": len(graph_triples),
                     "chapters": matched_chapters,
                     "chapter_details": [
                         {"citation": c, "snippet": m["snippet"]}
                         for c, m in zip(matched_chapters, matched)
                     ]
                 },
                 grader_trace]

        if rewrite_trace:
            steps.append(rewrite_trace)

        steps.append({
            "node": "Generate Node (文学考据合成生成)",
            "model": "CRAG-Knowledge-Core (离线规则引擎)",
            "citations": matched_chapters
        })

        return {
            "question": q,
            "final_answer": final_answer,
            "entities": entities,
            "engine": "rule-fallback",
            "steps": steps,
            "confidence": confidence,
            "citations": matched_chapters
        }

    # 事实型问题维度: (提问关键词, 方向, 关系类型集合, 入向句式, 出向句式)
    # 方向 "in": 【他人】-[关系]->【实体】; "out": 【实体】-[关系]->【他人】
    # 方向 "both": 对称关系(配偶/手足/宿敌等), 双向命中合并为一个子句
    # 方向 "dual": 方向敏感关系(如执掌), 入向出向分别成句
    # 句式中 {ent}=提问实体, {names}=命中他人名单
    FACTOID_DIMENSIONS = [
        (r"母亲|生母|娘亲|娘是谁", "in", {"MOTHER_OF"},
         "{ent}的生母是 {names}。", None),
        (r"父亲|生父|爹|爸爸", "in", {"FATHER_OF"},
         "{ent}的生父/养父是 {names}。", None),
        (r"妻子|夫人|老婆|正妻|嫁给|娶了|夫君|丈夫|老公|配偶", "both", {"SPOUSE_OF"},
         "{ent}的配偶是 {names}。", None),
        (r"儿子|女儿|孩子|子女", "out", {"FATHER_OF", "MOTHER_OF"},
         None, "{ent}的子女是 {names}。"),
        (r"恩师|师父|师傅|老师|师从|师承|拜谁|授业", "in", {"MASTER_OF"},
         "{ent}的恩师是 {names}。", None),
        (r"徒弟|弟子|学生", "out", {"MASTER_OF"},
         None, "{ent}的徒弟是 {names}。"),
        (r"守护|保护|护卫", "in", {"PROTECTS"},
         "守护{ent}的是 {names}。", None),
        (r"效忠|侍奉|听命|辅佐|忠心", "out", {"SERVES"},
         None, "{ent}效忠/侍奉的是 {names}。"),
        (r"统领|执掌|掌管|领导|率领|管理|由谁", "dual", {"LEADS", "GOVERNS"},
         "执掌{ent}的是 {names}。", "{ent}执掌着 {names}。"),
        (r"隶属|属于|麾下", "out", {"BELONGS_TO"},
         None, "{ent}隶属于 {names}。"),
        (r"宿敌|仇人|敌人|死敌|仇怨", "both", {"ENEMY_OF"},
         "{ent}的宿敌是 {names}。", None),
        (r"朋友|挚友|知己|交好|莫逆", "both", {"FRIEND_OF"},
         "{ent}的至交是 {names}。", None),
        (r"妹妹|弟弟|哥哥|姐姐|胞妹|胞弟|兄妹|兄弟|姐妹|手足|同胞", "both", {"SIBLING_OF"},
         "{ent}的手足是 {names}。", None),
    ]

    def _try_factoid_answer(self, q: str, entities: List[str],
                            full_graph: Dict[str, Any],
                            matched: List[Dict[str, Any]]) -> Optional[str]:
        """
        事实型快答: 像"范闲的母亲是谁？"这类短问题, 直接从图谱三元组
        给出规范答案 (如"叶轻眉"), 附图谱依据与真实章节引用。
        仅对短小、含"谁"、且能映射到具体关系维度的问题生效。
        """
        if not entities or len(q) > 30 or "谁" not in q:
            return None
        ent = entities[0]

        dims = [(direction, types, in_tpl, out_tpl)
                for pat, direction, types, in_tpl, out_tpl in self.FACTOID_DIMENSIONS
                if re.search(pat, q)]
        if not dims:
            return None

        # 收集图谱命中 (保留真实三元组方向与证据)
        direct_clauses: List[str] = []
        evidence_lines: List[str] = []
        for direction, types, in_tpl, out_tpl in dims:
            in_names: List[str] = []
            out_names: List[str] = []
            for l in full_graph["links"]:
                if l["type"] not in types:
                    continue
                ev = f"（原著依据: {l.get('evidence', '')}）" if l.get("evidence") else ""
                line = f"- 【{l['source']}】 ──[{l['label']}]──> 【{l['target']}】 {ev}"
                if direction in ("in", "both", "dual") and l["target"] == ent:
                    if l["source"] not in in_names:
                        in_names.append(l["source"])
                    if line not in evidence_lines:
                        evidence_lines.append(line)
                if direction in ("out", "both", "dual") and l["source"] == ent:
                    if l["target"] not in out_names:
                        out_names.append(l["target"])
                    if line not in evidence_lines:
                        evidence_lines.append(line)

            if direction == "both":
                # 对称关系: 双向命中合并为一个子句, 避免重复
                merged: List[str] = []
                for n in in_names + out_names:
                    if n not in merged:
                        merged.append(n)
                if merged and in_tpl:
                    direct_clauses.append(f"**{in_tpl.format(ent=ent, names='、'.join(merged))}**")
            else:
                if in_names and in_tpl:
                    direct_clauses.append(f"**{in_tpl.format(ent=ent, names='、'.join(in_names))}**")
                if out_names and out_tpl:
                    direct_clauses.append(f"**{out_tpl.format(ent=ent, names='、'.join(out_names))}**")

        if not direct_clauses:
            return None

        ch_cite = "、".join([f"**{chapter_retriever.format_citations([m])[0]}**" for m in matched[:2]]) \
            if matched else None
        if ch_cite:
            cite_block = f"> 🔖 **原著出处考据**：\n> 载于 {ch_cite}。"
        else:
            cite_block = "> 🔖 **原著出处考据**：\n> 该关系收录于原著人物图谱，暂未定位到具体章节原文。"

        return f"""### ⚡ 【直问直答 · {ent}】

{''.join(direct_clauses)}

#### 🕸️ 图谱依据：
{chr(10).join(evidence_lines[:6])}

---
{cite_block}"""

    def _generate_answer(self, q: str, entities: List[str],
                         triples: List[str], matched: List[Dict[str, Any]]) -> str:
        """基于真实命中的章节与图谱三元组合成回答; 无命中时如实说明"""
        if matched:
            ch_cite = "、".join([f"**{chapter_retriever.format_citations([m])[0]}**" for m in matched[:2]])
        else:
            ch_cite = None

        def cite_block() -> str:
            if ch_cite:
                return f"> 🔖 **原著出处考据**：\n> 载于 {ch_cite}。"
            return "> 🔖 **原著出处考据**：\n> 未能在本地全书语料中精确定位到具体章节，以上考据基于全书人物图谱与既有研究整理，仅供参考。"

        # 场景一：范闲身世
        if ("身世" in q or "生父" in q or "生母" in q or "父母" in q) and ("范闲" in entities or not entities):
            return f"""### 📜 【余年秘档 · 范闲身世大白】

在猫腻原著《庆余年》中，**范闲**的身世是贯穿全书七卷最核心的暗线：

1. **生母 —— 叶轻眉（神庙走出之奇女子）**
   范闲的亲生母亲是自极北神庙携五竹南下的穿越奇女子**叶轻眉**。她在太平别院产下范闲，留下了足以改变庆国格局的现代工商业遗产（内库）与监察院。

2. **生父 —— 庆帝（南庆至尊 · 王道大宗师）**
   范闲的真正生父并非名义上的司南伯范建，而是高坐龙椅的南庆皇帝**庆帝**。庆帝当年在诚王府为潜邸世子时，与叶轻眉相知相恋，范闲体内承袭了皇室血脉与至刚至猛的霸道真气心法。

3. **养父与守护之恩 —— 范建、陈萍萍与五竹**
   当年太平别院遭皇太后、皇后一族与军方高手趁庆帝西征之时血洗，**五竹**以玄铁铁钎杀破重围救下襁褓中的范闲；**范建**忍痛以自己的亲生幼子替换下范闲赴死，并将其寄养于远在海隅的澹州范府老太太处；**陈萍萍**则调动监察院黑骑封锁后路，隐忍二十年为这孤儿保驾护航。

---
{cite_block()}"""

        # 场景二：五竹与眼罩之谜
        if "五竹" in entities and ("眼罩" in q or "眼睛" in q or "身份" in q or "神庙" in q or "秘密" in q):
            return f"""### 🕶️ 【余年秘档 · 五竹神躯与天罚之眼】

**五竹**是《庆余年》全书中最超凡脱俗且战力绝顶的存在：

1. **真实身份：神庙最高阶生化仿生机器人**
   五竹并非寻常凡胎，而是旧人类上一个文明纪元遗留在极北神庙的**军用级仿生战斗机器人**。他体内无经脉真气，却拥有纳米级超合金骨骼与永不枯竭的核心能源，故能容颜三十年如一日不衰，体魄硬抗大宗师真气轰击。

2. **黑布蒙眼之谜：毁灭性高能镭射（激光眼）**
   五竹常年以一块黑布蒙目，外人皆以为他是盲人，实则他的双眼是毁灭性极强的高能聚变激光发生器。只要黑布扯下，眼眸中迸发的炽烈神光能瞬间熔金断铁、洞穿山岳。在原著第七卷皇宫终局决战中，重伤失忆的五竹最终扯下眼罩，一道彩虹般的璀璨激光将企图窥探神明之力的庆帝当场彻底轰杀。

3. **与叶轻眉、范闲的宿命羁绊**
   五竹被叶轻眉从神庙带入人间，逐渐诞生了独立的人性意识。他一生唯一的指令与本能就是“保护小姐”以及小姐托付的“少爷范闲”。

---
{cite_block()}"""

        # 场景三：陈萍萍与庆帝恩怨
        if "陈萍萍" in entities and ("刺杀" in q or "庆帝" in q or "轮椅" in q or "复仇" in q or "死" in q):
            return f"""### 🦅 【余年秘档 · 陈萍萍千古绝唱与轮椅之枪】

监察院第一任院长**陈萍萍**与庆帝之间的恩怨，是全书最具悲剧宿命感的权谋巅峰对决：

1. **复仇之源：叶轻眉惨死之真相**
   陈萍萍一生只敬重崇信叶轻眉一人。当他历经数十年暗中追查，终于确证当年太平别院的屠杀，表面是太后与皇后所为，实则是庆帝故意抽调走所有禁卫与高手、借刀杀人的冷酷阴谋后，陈萍萍的心便彻底死了，唯余为小姐复仇这一毕生夙愿。

2. **轮椅暗器：叶轻眉留下的两管转轮霰弹火枪**
   陈萍萍终日所坐的精钢轮椅扶手内，暗藏叶轻眉当年亲手为他改装的两管微型霰弹火枪。在第七卷中，陈萍萍单车入皇宫，当面痛斥庆帝的薄情寡义，随后猛扣扳机，漫天铁砂重创庆帝。庆帝凭借王道真气护体幸免，盛怒之下将陈萍萍凌迟处死。

3. **对范闲的倾尽所有**
   陈萍萍甚至宁愿让自己被千刀万剐，借自身的惨烈死讯彻底断绝范闲对庆帝最后的父子温情幻想，逼迫范闲真正下定决心推翻庆帝的极权统治。

---
{cite_block()}"""

        # 场景四：叶轻眉与神庙/理想
        if "叶轻眉" in entities:
            return f"""### 🌸 【余年秘档 · 叶轻眉的人间理想与悲歌】

**叶轻眉**是整部《庆余年》世界的源起与引路明灯：

1. **神庙之行与现代科技火种**
   她原本是旧时代工科高材生，沉眠苏醒于极北神庙，带出了五竹、狙击枪巴雷特以及天一道、大宗师等武学功法秘笈。她赠功法于苦荷、四顾剑，助他们登临大宗师；赠重狙助庆帝扫平夺嫡阻碍，促成了南庆的强盛。

2. **天下人人如龙的宏愿**
   她创办内库，让肥皂、玻璃、烈酒、白糖风靡大陆，奠定庆国富庶基石；建立监察院，在院前石碑上亲手刻下：“我希望庆国的人民，每一天都能活得有尊严，面对不公敢于拔剑，面对强权不必下跪。”

3. **悲剧根源：超越时代的思想被封建皇权反噬**
   这种主张“民贵君轻”、“人人平等”的思想彻底撼动了庆帝与封建皇权的统治合法性。庆帝无法容忍一个声望与财富凌驾于皇帝之上的女人，最终酿成了太平别院的千古遗恨。

---
{cite_block()}"""

        # 通用场景：根据提取的三元组与真实命中章节合成
        triples_summary = "\n".join([f"- {t}" for t in triples[:5]]) if triples \
            else f"- {'、'.join(entities) if entities else '相关人物'} 是《庆余年》中不可或缺的关键存在"
        return f"""### 📖 【余年秘档 · 关系图谱深度考据】

关于您探寻的问题，**GraphRAG 知识图谱**与原著卷册考据如下：

#### 🕸️ 知识图谱关联网络：
{triples_summary}

#### 📜 原著情节点评：
在《庆余年》原著小说中，涉及 **{'、'.join(entities) if entities else '相关'}** 的交互均带有极强的朝堂权谋与人性抉择色彩。人物之间的羁绊不仅仅局限于表面的名分，更牵扯到昔年叶轻眉留下的遗泽、内库财权的明争暗夺，以及监察院八处谍网在庆国与北齐之间的暗中角力。

---
{cite_block()}
> 如需进一步探求细节，可点击左侧人物关系图谱中的对应节点，查看其专属的人物密档卷轴与延伸提问。"""


# ============================================================
# 引擎二: LangGraph CRAG 真管线桥接 (Ollama 可达时自动启用)
# ============================================================

class LangGraphCRAGEngine:
    """
    将 Web 请求桥接到 graph/crag_graph.py 的 LangGraph Retrieve-Grade-Recover 闭环:
    Memory(指代消解) → 双路召回(FAISS+Neo4j) → Rerank → Grader → Rewrite/WebSearch → Generate → 记忆更新。

    - 编译图与 Neo4j 服务懒加载 (首次查询时), 避免拖慢 Web 启动;
    - 以 session_id 为 thread_id, 借助 MemorySaver checkpointer 实现多轮对话记忆;
    - 每轮重置易变状态字段, 防止上一轮的 web_context/contexts 泄漏进下一轮。
    """

    def __init__(self):
        self._app = None
        self._build_error: Optional[str] = None
        self._lock = threading.Lock()
        self._seen_sessions = set()

    def available(self) -> bool:
        return is_ollama_active()

    def _ensure_app(self):
        if self._app is not None:
            return self._app
        with self._lock:
            if self._app is not None:
                return self._app
            try:
                from graph import build_crag_graph
                self._app = build_crag_graph()
                print("[CRAG] LangGraph CRAG 闭环管线构建完成 (Ollama 模式)")
            except Exception as e:
                self._build_error = str(e)
                print(f"[CRAG] LangGraph 管线构建失败: {e}")
                raise
        return self._app

    def query(self, question: str, session_id: str = "user_web_session") -> Dict[str, Any]:
        app = self._ensure_app()
        thread_id = session_id or "user_web_session"
        config = {"configurable": {"thread_id": thread_id}}

        if thread_id in self._seen_sessions:
            # 多轮: 只给新问题并重置易变字段; chat_summary 等记忆由 checkpointer 保留
            state: Dict[str, Any] = {
                "question": question,
                "contexts": [],
                "is_sufficient": False,
                "confidence": 0.0,
                "missing_info": None,
                "rewritten_question": None,
                "final_answer": None,
                "iteration": 0,
                "web_context": None
            }
        else:
            state = {
                "question": question,
                "contexts": [],
                "is_sufficient": False,
                "confidence": 0.0,
                "missing_info": None,
                "rewritten_question": None,
                "final_answer": None,
                "iteration": 0,
                "web_context": None,
                "chat_summary": None,
                "standalone_question": None
            }
            self._seen_sessions.add(thread_id)

        result = app.invoke(state, config)
        return self._map_result(question, result)

    def _map_result(self, original_question: str, r: Dict[str, Any]) -> Dict[str, Any]:
        """把 GraphState 结果映射为前端 CRAG 推演卡片契约"""
        contexts = r.get("contexts") or []
        entities = _extract_entities(original_question)
        standalone = r.get("standalone_question") or original_question
        rewritten = r.get("rewritten_question")
        web_context = r.get("web_context")

        # 真实引用: 从向量命中的卷章元数据 + 联网来源提取
        citations: List[str] = []
        for ctx in contexts:
            title = ctx.get("chapter_title")
            if title:
                vol = ctx.get("volume", "")
                cite = f"《庆余年》{vol} · {title}" if vol else title
                if cite not in citations:
                    citations.append(cite)
        used_web = bool(web_context) and not str(web_context).startswith("联网搜索失败")
        if used_web and not citations:
            citations.append("网络资料 (Tavily 实时搜索)")

        graph_triples = [ctx["content"] for ctx in contexts if ctx.get("retriever_type") == "graph"]
        confidence = float(r.get("confidence") or 0.0)
        is_sufficient = bool(r.get("is_sufficient"))

        steps: List[Dict[str, Any]] = [
            {
                "node": "Memory Node (指代消解与记忆召回)",
                "status": "success",
                "detected_entities": entities,
                "standalone_question": standalone,
                "description": (
                    f"多轮指代消解: 「{original_question}」→「{standalone}」"
                    if standalone != original_question
                    else f"已识别核心小说实体: {'、'.join(entities) if entities else '泛化剧情'}"
                )
            },
            {
                "node": "Retrieve Node (Neo4j 图谱三元组召回)",
                "triples": graph_triples[:6],
                "total_triples": len(graph_triples),
                "chapters": citations[:3],
                "retrieved_docs": len(contexts)
            },
            {
                "node": "Grader Node (CRAG 质量评估器)",
                "is_sufficient": is_sufficient,
                "confidence_score": confidence,
                "status": "PASS" if (is_sufficient and confidence > 0.7) else "REWRITE",
                "reasoning": r.get("grader_reasoning") or "LLM 结构化评估完成",
                "missing_info": r.get("missing_info")
            }
        ]

        if rewritten and rewritten != standalone and rewritten != original_question:
            steps.append({
                "node": "Rewrite Node (提问自动优化)",
                "rewritten_question": rewritten,
                "trigger_web_search": False
            })
        if web_context:
            steps.append({
                "node": "Web Search Node (Tavily 联网兜底)",
                "summary": str(web_context)[:120],
                "trigger_web_search": True
            })

        steps.append({
            "node": "Generate Node (文学考据合成生成)",
            "model": f"{LLM_NAME} (Ollama 本地推理)",
            "citations": citations[:3]
        })

        final_answer = clean_think(r.get("final_answer") or "抱歉，本地和联网均未找到相关信息。")

        return {
            "question": original_question,
            "final_answer": final_answer,
            "entities": entities,
            "engine": "langgraph-crag",
            "steps": steps,
            "confidence": confidence,
            "citations": citations[:3],
            "standalone_question": standalone,
            "rewritten_question": rewritten
        }


# ============================================================
# 统一门面: 自动选路 + 失败降级
# ============================================================

class WebCRAGService:
    """对外统一入口: Ollama 可达走 LangGraph 闭环, 否则/失败时降级离线规则引擎"""

    def __init__(self):
        self._langgraph = LangGraphCRAGEngine()
        self._fallback = RuleBasedCRAGEngine()

    def engine_name(self) -> str:
        if self._langgraph.available():
            return f"LangGraph CRAG (Ollama · {LLM_NAME})"
        return "本地规则引擎 (离线兜底)"

    def query(self, question: str, session_id: str = "user_web_session") -> Dict[str, Any]:
        q = (question or "").strip()
        if not q:
            q = "《庆余年》主要人物有哪些？"

        if self._langgraph.available():
            try:
                return self._langgraph.query(q, session_id)
            except Exception as e:
                print(f"[CRAG] LangGraph 管线调用失败, 自动降级离线引擎: {e}")

        return self._fallback.query(q, session_id)


# 全局单例
crag_service = WebCRAGService()
web_crag_service = crag_service
