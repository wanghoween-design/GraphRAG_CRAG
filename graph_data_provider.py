# -*- coding: utf-8 -*-
"""
Graph Data Provider for 《庆余年》 GraphRAG & CRAG Novel Knowledge System.
Integrates live Neo4j queries with canonical core relations, novel chapter facts,
and character lore.

清洗与归纳规则 (v2):
1. 名称归并: 别名/泛称/异写统一映射到原著规范人名 (如 晨儿→林婉儿, 财政部→户部)。
2. 杂讯剔除: 泛称实体 (一个儿子/中年人/贵人…) 与家族集合名词 (范家/叶家…) 不入图。
3. 阵营归纳: 人物密档 > 补充密档 > 实体类型推断 (Place/Faction→名城重镇) > 兜底。
4. 边去重: 同 (源,目标,关系类型) 多章重复断言合并为一条并累计 weight。
5. 孤立节点剔除: 未入密档且无任何有效连线的节点不展示。
6. 结果缓存: 短 TTL + core_relations.json mtime 感知, 避免每请求全量重建。
"""
import os
import re
import json
import time
from typing import Dict, List, Any, Optional
from neo4j import GraphDatabase
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD

# 角色阵营划分与视觉色彩映射 (新中式配色方案)
FACTIONS = {
    "fan_manor": {
        "id": "fan_manor",
        "name": "范府世家",
        "color": "#f59e0b",     # 琥珀金
        "glow": "rgba(245, 158, 11, 0.4)",
        "badge": "范府"
    },
    "imperial": {
        "id": "imperial",
        "name": "南庆皇廷",
        "color": "#ef4444",     # 朱砂赤
        "glow": "rgba(239, 68, 68, 0.4)",
        "badge": "皇廷"
    },
    "council": {
        "id": "council",
        "name": "监察暗网",
        "color": "#8b5cf6",     # 霁夜紫
        "glow": "rgba(139, 92, 246, 0.4)",
        "badge": "监察院"
    },
    "grandmaster": {
        "id": "grandmaster",
        "name": "世外宗师与神庙",
        "color": "#10b981",     # 秘色翠
        "glow": "rgba(16, 185, 129, 0.4)",
        "badge": "宗师/神庙"
    },
    "beiqi_romance": {
        "id": "beiqi_romance",
        "name": "红颜知己与江湖",
        "color": "#06b6d4",     # 烟青碧
        "glow": "rgba(6, 182, 212, 0.4)",
        "badge": "红颜/江湖"
    },
    "places_org": {
        "id": "places_org",
        "name": "名城重镇与司部",
        "color": "#64748b",     # 黛石灰
        "glow": "rgba(100, 116, 139, 0.4)",
        "badge": "城司"
    }
}

# 关系类型中文翻译与线段色彩
RELATION_MAP = {
    "MOTHER_OF": {"label": "生母", "color": "#ef4444", "dash": ""},
    "FATHER_OF": {"label": "生父/义父", "color": "#f59e0b", "dash": ""},
    "CHILD_OF": {"label": "骨肉血亲", "color": "#f43f5e", "dash": ""},
    "PROTECTS": {"label": "誓死守护", "color": "#10b981", "dash": ""},
    "SERVES": {"label": "忠心侍奉", "color": "#06b6d4", "dash": ""},
    "LEADS": {"label": "统领执掌", "color": "#8b5cf6", "dash": ""},
    "GOVERNS": {"label": "掌控治理", "color": "#eab308", "dash": ""},
    "BELONGS_TO": {"label": "隶属于", "color": "#64748b", "dash": "4 2"},
    "ENEMY_OF": {"label": "生死宿敌", "color": "#dc2626", "dash": "6 3"},
    "SIBLING_OF": {"label": "手足同胞", "color": "#ec4899", "dash": ""},
    "FRIEND_OF": {"label": "莫逆之交", "color": "#3b82f6", "dash": ""},
    "MASTER_OF": {"label": "恩师传道", "color": "#14b8a6", "dash": ""},
    "SPOUSE_OF": {"label": "结发夫妻", "color": "#f43f5e", "dash": ""},
    "KILLS": {"label": "设局诛杀", "color": "#b91c1c", "dash": "5 3"},
    "LOCATED_IN": {"label": "驻留常在", "color": "#94a3b8", "dash": "3 3"},
    "REBORN_AS": {"label": "宿慧转生", "color": "#a855f7", "dash": "4 4"},
    "ALLIED_WITH": {"label": "暗中结盟", "color": "#eab308", "dash": ""}
}

# 经典角色深度密档与小说人设 (原著人物志)
CHARACTER_LORE = {
    "范闲": {
        "aliases": ["范慎", "安之", "小范大人", "诗仙", "提司大人", "小范闲"],
        "faction": "fan_manor",
        "title": "监察院提司 · 内库执掌 · 穿越天脉者",
        "salience": 10,
        "avatar_glyph": "闲",
        "summary": "《庆余年》绝对主角。表面为户部尚书范建之私生子，实为叶轻眉与庆帝之子。兼具前世现代青年范慎之记忆与霸道真气。性格崇尚自由，喜谈笑弄权，重情重义。手握监察院提司腰牌与内库大权，在京都权谋漩涡中破局逆行。",
        "quotes": [
            "“我这辈子就想做个富贵闲人，可你们偏偏逼我掌权杀人。”",
            "“我手里的黑箱子，是母亲留给这世间最温柔也是最残忍的答案。”"
        ]
    },
    "叶轻眉": {
        "aliases": ["小叶子", "老妈", "叶家女主", "神庙仙女"],
        "faction": "grandmaster",
        "title": "神庙求索者 · 商号内库与监察院缔造者",
        "salience": 10,
        "avatar_glyph": "眉",
        "summary": "全书灵魂母题。来自文明重启前的现代工科女性，从极北神庙携五竹与重狙巴雷特南下。助南庆开疆拓土，建立内库商号与监察院，立言“愿天下人人如龙，生而平等”。因触动皇权根基，遭庆帝、太后及京都贵族阴谋合杀于太平别院。",
        "quotes": [
            "“我希望庆国的人民，每一天都能活得有尊严，不必跪任何人。”",
            "“生命本身就是一场奇迹，何必非要神明来定义尊卑？”"
        ]
    },
    "庆帝": {
        "aliases": ["主子", "皇帝", "南庆天子", "陛下"],
        "faction": "imperial",
        "title": "南庆至尊 · 四大宗师之王道宗师 · 权谋终极操盘手",
        "salience": 10,
        "avatar_glyph": "庆",
        "summary": "南庆雄主，范闲生父。天下四大宗师中隐藏最深之人，经脉尽碎后重修成王道真气。胸怀统一天下之野望，心机极度深沉冷酷。借神庙与太后之手除去叶轻眉，将亲生骨肉与满朝权臣玩弄于股掌之间。",
        "quotes": [
            "“这天下是朕的天下，任何妄图凌驾于皇权之上的人，都得死。”",
            "“安之，你以为陈萍萍在帮你？他只是在用你替那个女人向朕复仇。”"
        ]
    },
    "五竹": {
        "aliases": ["瞎子", "五竹叔", "少年仆人", "黑布叔", "五大人"],
        "faction": "grandmaster",
        "title": "神庙最高战力仿生人 · 叶轻眉最忠诚侍从 · 终身守护者",
        "salience": 10,
        "avatar_glyph": "竹",
        "summary": "神庙遗留的高科技仿生战斗机器人，双眼为毁灭性高能镭射光（故终生覆黑布）。容颜数十载不老，身法天下第一，持一把玄铁黑钎，不通内力却可秒杀宗师。对叶轻眉与范闲怀有超越机械程序的真挚温情与守护本能。",
        "quotes": [
            "“小姐死了。谁杀的，我就杀谁。”",
            "“范闲，我打不过神庙，但只要我活着，就没人能动你。”"
        ]
    },
    "陈萍萍": {
        "aliases": ["陈院长", "老瘸子", "老院长", "黑骑之主"],
        "faction": "council",
        "title": "监察院院长 · 特务之王 · 轮椅上的天下第一阴谋家",
        "salience": 10,
        "avatar_glyph": "萍",
        "summary": "天下特务机关监察院第一任院长。双腿残废乘精钢轮椅，扶持黑骑威震四海。一生只敬重崇拜叶轻眉一人。得知叶轻眉被害真相后，隐忍二十载，布下惊天大局，最终驾轮椅进宫，以轮椅暗藏火枪决死刺杀庆帝，为小叶子讨公道。",
        "quotes": [
            "“我这条残命，本就是小姐给的。这二十年，我不过是替她看着这个人间。”",
            "“陛下，这满朝文武，天下万民，可曾有人真正把小叶子当过人？”"
        ]
    },
    "范建": {
        "aliases": ["司南伯", "尚书大人", "老范大人"],
        "faction": "fan_manor",
        "title": "户部尚书 · 司南伯爵 · 范府家主 · 范闲养父",
        "salience": 8,
        "avatar_glyph": "建",
        "summary": "范闲的名义生父与坚实后盾，昔年诚王府世子潜邸重臣。当年在别院之难中，忍痛用自己的亲生骨肉替换下范闲救其一命。掌管天下钱粮户部与绝密战力虎卫，视范闲胜过亲子。",
        "quotes": [
            "“闲儿，天下人都视你为棋子，唯独范府是你的家。”"
        ]
    },
    "林婉儿": {
        "aliases": ["鸡腿姑娘", "晨郡主", "婉儿", "晨儿"],
        "faction": "beiqi_romance",
        "title": "庆国晨郡主 · 长公主与林若甫之女 · 范闲正妻",
        "salience": 8,
        "avatar_glyph": "婉",
        "summary": "长公主李云睿与宰相林若甫之私生女。自幼患有肺痨，在庆庙中与范闲因一只鸡腿结缘，定情终生。温婉坚韧，深明大义，在纷繁复杂的朝堂争斗中始终是范闲的心灵港湾。",
        "quotes": [
            "“你若要与这天下为敌，我便在身后替你备好退路。”"
        ]
    },
    "范若若": {
        "aliases": ["若若", "京都第一才女", "范小姐"],
        "faction": "fan_manor",
        "title": "京都第一才女 · 范闲之妹 · 神级狙击手徒弟",
        "salience": 7,
        "avatar_glyph": "若",
        "summary": "范建之女，范闲名义上的妹妹。琴棋书画无一不精，性格清冷聪慧，只对哥哥范闲言听计从。后在范闲传授下精通巴雷特重狙，在大东山之战及皇宫刺杀中多次力挽狂澜。",
        "quotes": [
            "“哥，只要是你说对的，若若就绝不会怀疑半分。”"
        ]
    },
    "费介": {
        "aliases": ["老费", "费老", "费先生"],
        "faction": "council",
        "title": "监察院三处主办 · 天下第一用毒宗师 · 范闲启蒙之师",
        "salience": 7,
        "avatar_glyph": "介",
        "summary": "监察院三处主办，精通天下毒理与解药。当年奉陈萍萍之命前往澹州教导幼年范闲医术与毒道。外表邋遢古怪，实则极度护犊，曾言“谁敢伤范闲一根毫毛，我让他全家不得好死”。",
        "quotes": [
            "“学毒不是为了杀人，是为了保你自己的小命！”"
        ]
    },
    "长公主": {
        "aliases": ["李云睿", "云睿", "内库掌权人"],
        "faction": "imperial",
        "title": "南庆长公主 · 林婉儿生母 · 内库前执掌者",
        "salience": 8,
        "avatar_glyph": "睿",
        "summary": "庆帝胞妹，容貌绝美而手段酷烈偏执。极度渴望超越叶轻眉在庆帝心中的地位，表面支持太子，暗中联手二皇子、勾结北齐，最终阴谋败露自尽于宫中。",
        "quotes": [
            "“我得不到的，我就亲手把它彻底毁掉。”"
        ]
    },
    "太子": {
        "aliases": ["李承乾", "储君"],
        "faction": "imperial",
        "title": "南庆储君 · 庆帝嫡长子",
        "salience": 6,
        "avatar_glyph": "乾",
        "summary": "南庆太子，深宫权谋博弈的牺牲品。性格阴郁压抑，暗恋长公主李云睿。在庆帝布下的磨刀石棋局中逐渐扭曲疯狂。",
        "quotes": [
            "“这皇位如坐针毡，可孤除了坐上去，退后一步便是深渊。”"
        ]
    },
    "二皇子": {
        "aliases": ["李承泽", "老二"],
        "faction": "imperial",
        "title": "南庆二皇子 · 狂狷风流 · 权谋棋手",
        "salience": 7,
        "avatar_glyph": "泽",
        "summary": "庆帝故意用来磨砺太子的“磨刀石”。不喜穿鞋，酷爱在闹市小楼大快朵颐。看似潇洒不羁，实则深谙阴谋，与范闲多番交手，后在大东山事发后自尽留下绝笔信。",
        "quotes": [
            "“阋墙之祸，非我所愿；奈何生于帝王家，不死不休。”"
        ]
    },
    "苦荷": {
        "aliases": ["战清风", "苦荷国师", "北齐大宗师"],
        "faction": "grandmaster",
        "title": "四大宗师之一 · 北齐国师 · 天一道宗师",
        "salience": 8,
        "avatar_glyph": "苦",
        "summary": "北齐皇室血脉，当年与肖恩历尽千辛万苦远赴极北神庙，得叶轻眉赠予天一道天卷功法踏入大宗师境。一生庇护北齐国祚。",
        "quotes": [
            "“神庙之门开处，仙凡之别立现。”"
        ]
    },
    "四顾剑": {
        "aliases": ["剑痴", "城主", "大白痴"],
        "faction": "grandmaster",
        "title": "四大宗师之一 · 东夷城城主 · 唯我极剑",
        "salience": 8,
        "avatar_glyph": "剑",
        "summary": "东夷城城主，幼年受尽族人凌辱，唯有大树下数蚂蚁。叶轻眉赠其剑谱并点拨，终成以剑入道的无上宗师。一剑守一城，庇护东夷城免遭南庆吞并。",
        "quotes": [
            "“我这一生，唯剑而已。顾前顾后，终成绝响。”"
        ]
    },
    "叶流云": {
        "aliases": ["流云散手", "歌者"],
        "faction": "grandmaster",
        "title": "四大宗师之一 · 南庆叶家老祖 · 流云散手创作者",
        "salience": 7,
        "avatar_glyph": "云",
        "summary": "南庆叶家定海神针。早年与五竹交手被用铁钎痛揍，顿悟弃剑，创出天下无双的流云散手。大东山之战关键卧底，事后飘然远游海外。",
        "quotes": [
            "“飘飘乎如遗世独立，羽化而登仙。”"
        ]
    },
    "海棠朵朵": {
        "aliases": ["朵朵", "北齐圣女"],
        "faction": "beiqi_romance",
        "title": "北齐天一道圣女 · 苦荷关门弟子 · 范闲至交红颜",
        "salience": 7,
        "avatar_glyph": "棠",
        "summary": "九品上绝顶高手，身穿布衣木屐，行走于市井山野。性格洒脱不羁、热爱田园生活。与范闲不打不相识，既是政见盟友，又是生死契阔的红颜知己。",
        "quotes": [
            "“范闲，做人何必活得那么累？吃酒打渔，不亦乐乎。”"
        ]
    },
    "王启年": {
        "aliases": ["老王", "王文书", "神行百里"],
        "faction": "council",
        "title": "监察院一处文书 · 追踪第一人 · 范闲头号贴心心腹",
        "salience": 7,
        "avatar_glyph": "王",
        "summary": "监察院老油条，表面极度贪财惧内，实则轻功举世罕见，追踪痕迹天下第一。对范闲忠心耿耿，多次在生死危难关头充当通信与逃生奇兵。",
        "quotes": [
            "“大人，给银子咱替您卖命！不给银子……咱也得替您把事情办利索！”"
        ]
    },
    "藤子京": {
        "aliases": ["滕梓荆", "藤护卫"],
        "faction": "council",
        "title": "监察院剑手 · 范闲贴身护卫",
        "salience": 6,
        "avatar_glyph": "藤",
        "summary": "奉命护卫范闲入京的监察院好手，车前马后，忠勇干练。京都牛栏街刺杀中身负重伤犹自力战不退，是范闲最早以性命相托的伙伴。",
        "quotes": []
    },
    "司理理": {
        "aliases": ["理理", "花魁", "北齐贵妃"],
        "faction": "beiqi_romance",
        "title": "京都醉仙居花魁 · 北齐潜伏密谍 · 后封北齐贵妃",
        "salience": 6,
        "avatar_glyph": "理",
        "summary": "南庆皇室遗孤，身世漂泊凄凉。在流晶河花船上掩护刺杀案，后被范闲生擒押送北齐。旅途中两人惺惺相惜，情愫暗生，最终入深宫保全家族。",
        "quotes": [
            "“我的一生皆由不得自己，唯独那辆北上的马车里，有我唯一的真情。”"
        ]
    },
    "监察院": {
        "aliases": ["特务机构", "南庆监察院"],
        "faction": "council",
        "title": "特务司法机关 · 独立于六部之外的暗夜之剑",
        "salience": 7,
        "avatar_glyph": "院",
        "summary": "叶轻眉创立、陈萍萍执掌的国家监察特务系统。门前立石碑刻叶轻眉誓词。下辖八处，统管密报、情报、用毒、暗杀、刑狱、守备。",
        "quotes": ["“监察天下，直指人心。”"]
    },
    "内库": {
        "aliases": ["商号内库", "天下第一金库"],
        "faction": "fan_manor",
        "title": "天下财富源泉 · 叶轻眉现代工商业遗产",
        "salience": 6,
        "avatar_glyph": "库",
        "summary": "叶轻眉运用现代技术建立的跨国产业垄断机构，生产琉璃、烈酒、白糖、肥皂等暴利商品，支撑整个南庆国库与军费开支。",
        "quotes": ["“得内库者得天下富贵。”"]
    }
}

# 补充人物/势力密档: 抽取图谱中出现、值得入图但未收录进核心人物志的实体
SUPPLEMENTARY_LORE = {
    "老夫人": {
        "faction": "fan_manor", "salience": 7, "avatar_glyph": "奶",
        "title": "澹州范府老夫人 · 范闲祖母",
        "summary": "范建之母，常年居于澹州老家。以一介妇人身旁抑制州地界暗流，将范闲抚养成人，是范闲幼年最坚实的护身符，深不可测。"
    },
    "范思辙": {
        "faction": "fan_manor", "salience": 7, "avatar_glyph": "辙",
        "title": "范府二少爷 · 算账奇才",
        "summary": "范建与柳氏之子。顽劣纨绔却天赋异禀于算学账目，视财如命。后在范闲提点下寻得抱月楼等生意正途。"
    },
    "柳氏": {
        "faction": "fan_manor", "salience": 6, "avatar_glyph": "柳",
        "title": "范府主母 · 范思辙生母",
        "summary": "出身柳姓大族的范府主母，范思辙之母。治家严谨，初对范闲心存芥蒂，后渐生敬意。"
    },
    "林若甫": {
        "faction": "imperial", "salience": 8, "avatar_glyph": "甫",
        "title": "南庆当朝宰相 · 林婉儿生父",
        "summary": "百官之首，老谋深算的官场不倒翁。与长公主有一段旧情，私生女即林婉儿。为子女谋算深远，在庆帝与权臣的夹缝中步步为营。"
    },
    "皇太后": {
        "faction": "imperial", "salience": 7, "avatar_glyph": "后",
        "title": "南庆皇太后 · 别院血案元凶之一",
        "summary": "庆帝之母，与叶轻眉及其背后的新派势力势不两立。当年太平别院血案的幕后黑手之一，深宫之中最顽固的旧秩序守护者。"
    },
    "靖郡王": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "靖",
        "title": "皇室亲王 · 李弘成与柔嘉郡主之父",
        "summary": "庆帝胞弟，立志做富贵闲王的郡王。口无遮拦、性情直率，与范府往来密切，其世子李弘成与范闲交好。"
    },
    "靖王妃": {
        "faction": "imperial", "salience": 4, "avatar_glyph": "妃",
        "title": "靖郡王正妃",
        "summary": "靖郡王之正妃，李弘成与柔嘉郡主之母，深谙王府处世之道。"
    },
    "李弘成": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "弘",
        "title": "靖郡王世子 · 范闲好友",
        "summary": "靖郡王世子，京都有名的风流皇子辈。与范闲一见如故，常流连流晶河畔，看似闲散却心思通透。"
    },
    "柔嘉郡主": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "柔",
        "title": "靖王府郡主 · 京都闺秀",
        "summary": "靖郡王之女，温婉娴静的皇室郡主，常入范府与范若若闲叙。"
    },
    "郭保坤": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "郭",
        "title": "礼部郭攸之之子 · 太学书生",
        "summary": "恃才傲物的官家公子，自命清流才子。与范闲在诗会朝堂屡屡结怨，明争暗斗不绝。"
    },
    "贺宗纬": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "贺",
        "title": "京都名士 · 善审时度势的清流",
        "summary": "以文章见长的京都名士，善于审时度势，深得庆帝欣赏，是朝局中被刻意扶植的制衡棋子。"
    },
    "言若海": {
        "faction": "council", "salience": 6, "avatar_glyph": "言",
        "title": "监察院资深主办 · 院中老人",
        "summary": "监察院老牌高层，处事沉稳老辣，辅佐陈萍萍打理院务，是院内少有的两朝元老。"
    },
    "宫典": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "宫",
        "title": "皇宫禁军统领 · 剑法超群",
        "summary": "皇宫禁军统领，武艺高强，执掌宫禁宿卫。沉默寡言，只忠于庆帝一人。"
    },
    "叶重": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "重",
        "title": "京都守备统领 · 叶家家主",
        "summary": "京都守备师统领，军方实权人物，叶灵儿之父。叶家老祖即大宗师叶流云，家族地位超然。"
    },
    "叶灵儿": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "灵",
        "title": "将门虎女 · 叶重之女",
        "summary": "叶重之女，性子爽直的将门虎女，与林婉儿交好，是范闲初入京都时结识的友人。"
    },
    "袁梦": {
        "faction": "beiqi_romance", "salience": 5, "avatar_glyph": "梦",
        "title": "京都风月场中的玲珑人物",
        "summary": "京都风月场中八面玲珑的传奇女子，与诸方权贵皇子皆有往来，消息灵通。"
    },
    "黑骑": {
        "faction": "places_org", "salience": 6, "avatar_glyph": "骑",
        "title": "监察院玄甲黑骑 · 天下强军",
        "summary": "陈萍萍亲手缔造的重甲铁骑，机动天下第一，是监察院最锋利的一柄刀，一现于世便地动山摇。"
    },
    "户部": {
        "faction": "places_org", "salience": 6, "avatar_glyph": "户",
        "title": "南庆六部之户部 · 天下钱粮",
        "summary": "掌天下财政度支的六部之一，由司南伯范建执掌多年，府库丰盈，牵动朝局命脉。"
    },
    "朝廷文英总校处": {
        "faction": "council", "salience": 4, "avatar_glyph": "文",
        "title": "监察院第八处 · 文英总校处",
        "summary": "监察院八处之一，执掌文书文牍校勘之事，是监察院明面文书体系的一部分。"
    },
    "京都": {
        "faction": "places_org", "salience": 7, "avatar_glyph": "京",
        "title": "南庆国都 · 权力漩涡中心",
        "summary": "庆国政治中枢，皇城、监察院、六部与各方权贵盘踞之地，天下风云尽出于此。"
    },
    "澹州": {
        "faction": "places_org", "salience": 6, "avatar_glyph": "澹",
        "title": "东海之滨小城 · 范闲成长之地",
        "summary": "偏安东海一隅的澹州港，范闲幼年寄居于此，祖母与费介护他长大，是他心中最柔软的归处。"
    },
    "北齐": {
        "faction": "places_org", "salience": 7, "avatar_glyph": "齐",
        "title": "北方霸主 · 与南庆分庭抗礼",
        "summary": "大陆北方的强国，战豆豆治下朝堂与谍网自成一格，与南庆的和战博弈贯穿全书。"
    },
    "东夷城": {
        "faction": "places_org", "salience": 6, "avatar_glyph": "夷",
        "title": "临海自由之邦 · 四顾剑坐镇",
        "summary": "不设王侯的临海商贸自由城邦，倚仗大宗师四顾剑一剑守护，超然于庆齐争霸之外。"
    },
    "神庙": {
        "faction": "grandmaster", "salience": 8, "avatar_glyph": "庙",
        "title": "极北神秘存在 · 上纪元文明遗产",
        "summary": "世人敬畏信仰的天道所在，实为上个文明纪元遗留的军事博物馆。叶轻眉与五竹皆出自于此，是天底下最大的秘密。"
    },
    "肖恩": {
        "faction": "beiqi_romance", "salience": 6, "avatar_glyph": "肖",
        "title": "北齐密谍之祖 · 监察院宿敌",
        "summary": "北齐老牌密谍首领，与苦荷当年同赴神庙。被监察院囚禁天牢二十载，其交接押送之事牵动庆齐两国神经。"
    },
    "战豆豆": {
        "faction": "beiqi_romance", "salience": 6, "avatar_glyph": "豆",
        "title": "北齐少年天子 · 深藏不露",
        "summary": "北齐皇帝，年少继位却手腕老成，以女儿身君临北齐是全书最深藏的机密之一，与范闲亦敌亦友。"
    },
    "庄墨韩": {
        "faction": "grandmaster", "salience": 6, "avatar_glyph": "墨",
        "title": "天下文宗 · 北齐文学大家",
        "summary": "一生著书立说、桃李天下的文坛宗师。曾受胁迫于殿前构陷范闲，晚年痛悔，将毕生藏书托付范闲。"
    },
    "庆国": {
        "faction": "places_org", "salience": 8, "avatar_glyph": "庆",
        "title": "南庆 · 北伐雄主之国",
        "summary": "故事的主舞台，庆帝治下的强国，内库富甲天下、监察院威慑四方，与北齐东西对峙。"
    },
    "范府": {
        "faction": "places_org", "salience": 7, "avatar_glyph": "范",
        "title": "司南伯府 · 范府",
        "summary": "户部尚书范建的京都府邸，范闲入京后的家，范思辙、范若若与柳氏皆居于此。"
    },
    "皇宫": {
        "faction": "places_org", "salience": 7, "avatar_glyph": "宫",
        "title": "南庆皇宫 · 权力之巅",
        "summary": "庆帝居所与皇权中枢，宫典统领禁军宿卫，太后与皇后深居其间。"
    },
    "庆余堂": {
        "faction": "fan_manor", "salience": 6, "avatar_glyph": "余",
        "title": "叶家商号 · 庆余堂",
        "summary": "叶轻眉一手建立的商号，内库产业在京都的门面，由老掌柜叶大等人执掌，后为范闲所用。"
    },
    "叶大": {
        "faction": "fan_manor", "salience": 5, "avatar_glyph": "叶",
        "title": "庆余堂大掌柜",
        "summary": "庆余堂的老掌柜，叶家旧人，奉叶轻眉为旧主，后辅佐范闲接掌商号脉络。"
    },
    "澹泊书局": {
        "faction": "fan_manor", "salience": 5, "avatar_glyph": "书",
        "title": "京都新贵书局 · 范闲产业",
        "summary": "范闲与范思辙在京都合开的书局，凭《红楼》一时纸贵，成为京都文人的风流去处。"
    },
    "太常寺": {
        "faction": "places_org", "salience": 5, "avatar_glyph": "常",
        "title": "南庆九寺之太常寺",
        "summary": "掌礼乐祭祀的九寺之一，范闲入京后曾在太常寺挂职点卯。"
    },
    "郭攸之": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "郭",
        "title": "南庆礼部尚书 · 郭保坤之父",
        "summary": "礼部尚书，太子的老师，郭保坤之父。子凭父贵在京都骄纵，父子皆与范闲不睦。"
    },
    "梅执礼": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "梅",
        "title": "南庆朝中老臣",
        "summary": "南庆朝廷老臣，庆帝手下历练多年的干臣。"
    },
    "大皇子": {
        "faction": "imperial", "salience": 6, "avatar_glyph": "大",
        "title": "南庆皇长子",
        "summary": "庆帝皇长子，常年领兵在外，性子直烈，是夺嫡棋局中独特的一子。"
    },
    "林珙": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "珙",
        "title": "林家二公子 · 牛栏街案主使",
        "summary": "宰相林若甫之子，林婉儿二哥。为夺内库主导权设局牛栏街刺杀范闲，事败后被五竹诛杀。"
    },
    "大宝": {
        "faction": "imperial", "salience": 4, "avatar_glyph": "宝",
        "title": "林家大公子",
        "summary": "林若甫长子，林婉儿的大哥。心智如孩童却心地纯善，是林家最干净的人。"
    },
    "吴伯安": {
        "faction": "imperial", "salience": 4, "avatar_glyph": "吴",
        "title": "谋划牛栏街的幕僚",
        "summary": "长公主一系豢养的谋士，牛栏街刺杀案的计划者，事败后被灭口。"
    },
    "程巨树": {
        "faction": "beiqi_romance", "salience": 4, "avatar_glyph": "程",
        "title": "北齐高手 · 牛栏街刺客",
        "summary": "北齐来的九品高手，受雇参与牛栏街刺杀，力大无穷，最终死在范闲的匕首与霸道真气之下。"
    },
    "洪公公": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "洪",
        "title": "宫中老公公 · 太后近侍",
        "summary": "常年侍奉皇太后的老公公，深居宫禁，深不可测。"
    },
    "皇后": {
        "faction": "imperial", "salience": 7, "avatar_glyph": "后",
        "title": "南庆皇后 · 太子生母",
        "summary": "庆帝正宫皇后，太子生母。出身显赫，与太后宫闱同气连枝，是深宫中最威严也最冰冷的女人。"
    },
    "袁宏道": {
        "faction": "imperial", "salience": 5, "avatar_glyph": "袁",
        "title": "宰相府头号谋士",
        "summary": "林若甫最倚重的心腹幕僚，沉着多智，宰相府大小机宜皆出其手。"
    }
}

# 名称归并表: 别名/泛称/异写 → 原著规范人名 (基于章节证据)
NAME_MERGES = {
    # 范闲
    "范慎": "范闲", "小范大人": "范闲", "安之": "范闲", "小范闲": "范闲",
    "char_infant": "范闲", "char_fanxian": "范闲",
    # 林婉儿 ("晨儿"在原文中即指宰相私生女林家小姐, 证据见 ch63/ch66)
    "晨儿": "林婉儿", "鸡腿姑娘": "林婉儿", "晨郡主": "林婉儿", "婉儿": "林婉儿",
    # 叶轻眉
    "老妈": "叶轻眉", "小叶子": "叶轻眉", "叶家女主": "叶轻眉", "char_miss": "叶轻眉",
    # 庆帝 (ch0"主子的血肉"、ch55/57 庙中/车上"贵人"均指庆帝)
    "皇帝": "庆帝", "南庆皇帝": "庆帝", "陛下": "庆帝", "主子": "庆帝", "贵人": "庆帝",
    "char_master": "庆帝",
    # 五竹
    "瞎子": "五竹", "黑布叔": "五竹", "少年仆人": "五竹", "五大人": "五竹",
    "char_blind_youth": "五竹",
    # 陈萍萍 / 范建
    "老院长": "陈萍萍", "老瘸子": "陈萍萍", "陈院长": "陈萍萍", "char_wheelchair_man": "陈萍萍",
    "司南伯": "范建", "char_sinan_count": "范建",
    # 皇室与其他
    "太后": "皇太后", "char_countess_mother": "老夫人",
    "剑圣": "四顾剑", "剑痴": "四顾剑", "战清风": "苦荷",
    "李云睿": "长公主", "李承乾": "太子", "李承泽": "二皇子",
    "靖王爷": "靖郡王", "靖王爷家": "靖郡王", "靖郡王家": "靖郡王",
    # 机构与器物异写 (ch8"财政部"即户部, ch44"皇家商号"即内库产业, ch0"黑骑士"即黑骑)
    "财政部": "户部", "皇家商号": "内库", "商号内库": "内库", "黑骑士": "黑骑",
    # 称呼简称
    "老王": "王启年", "王文书": "王启年", "老费": "费介", "费老": "费介",
    "朵朵": "海棠朵朵", "北齐圣女": "海棠朵朵",
    "理理": "司理理", "花魁": "司理理", "若若": "范若若",
    "滕梓荆": "藤子京", "小滕": "藤子京",
    # 地名异写 (ch0-110 抽取中"澹州港"即澹州, "北齐国"即北齐)
    "澹州港": "澹州", "北齐国": "北齐", "南庆国": "庆国",
}

# 杂讯实体黑名单: 泛称占位、集合名词与抽取幻觉名, 不具备节点价值
JUNK_ENTITY_NAMES = {
    "一个儿子", "姨太太", "大夫人", "中年人", "夜行杀手", "元老会", "格物所",
    "四大宗师", "范家", "叶家", "柳家", "林家", "京都王公贵族",
    "李治", "皇后的父亲", "后宫", "太子那派", "二皇子一派",
}

# 抽取错误三元组黑名单: (源, 关系类型, 目标) —— 与原著明显不符的边不入图
WRONG_TRIPLES = {
    ("皇太后", "MOTHER_OF", "林婉儿"),  # 太后是婉儿的外祖母, 生母是长公主
}

# 泛称模式: 适用于后续章节持续抽取产生的同类杂讯
JUNK_NAME_PATTERNS = [
    r"^[一二两三四五六七八九十几]{1,3}[个名位条名]?$",
    r"^(一个|两个|几个|某个|一名|一位|一名|某个)[儿女子男少老中太].*",
    r"(的手下|的人|等人|一伙|众人|家眷|亲信)$",
    r"(那派|一派|一党|党羽|诸卿|众人)$",
    r"^(某|未知|无名|神秘)",
    r"^(男子|女子|老者|老翁|少年|小孩|孩子|孩童|太监|侍女|婢女|丫鬟|护卫|侍卫|亲兵|随从|仆人|车夫|马夫|官员|大臣|贵人|夫人|太太|姨太太|姑娘|小姐|公子|书生|学士|和尚|道士|刺客|杀手|中年人|老年人|老人家|穷书生|大汉|胖子|瘦子)$",
]

# 图谱缓存 TTL (秒): Neo4j 持续写入抽取结果时最多延迟两分钟刷新
GRAPH_CACHE_TTL = 120


class NovelGraphProvider:
    """
    提供完整的《庆余年》人物关系图谱数据与节点详情
    自动兼容 Neo4j 实时查询与本地核心高信度关系库
    """
    def __init__(self):
        self.uri = NEO4J_URI or "neo4j://127.0.0.1:7687"
        self.user = NEO4J_USERNAME or "neo4j"
        self.pwd = NEO4J_PASSWORD or "123456789"
        self.driver = None
        self._graph_cache = None
        self._cache_time = 0.0
        self._cache_core_mtime = None
        self._init_neo4j()

    def _init_neo4j(self):
        try:
            self.driver = GraphDatabase.driver(self.uri, auth=(self.user, self.pwd))
            # 测试连通性
            with self.driver.session() as s:
                s.run("RETURN 1").single()
            print("[GraphProvider] Neo4j 连接成功！")
        except Exception as e:
            print(f"[GraphProvider] Neo4j 连接失败或离线: {e}，将启用本地增强知识库")
            self.driver = None

    # ---------------- 名称清洗与杂讯判定 ----------------

    def _normalize_name(self, raw_name: str) -> str:
        """规范化人名指代: 去空白 → 别名归并"""
        name = (raw_name or "").strip()
        return NAME_MERGES.get(name, name)

    def _is_junk(self, name: str) -> bool:
        """杂讯实体判定: 密档名录永远保留, 黑名单与泛称模式剔除"""
        if not name:
            return True
        if name in CHARACTER_LORE or name in SUPPLEMENTARY_LORE:
            return False
        if name in JUNK_ENTITY_NAMES:
            return True
        return any(re.fullmatch(p, name) for p in JUNK_NAME_PATTERNS)

    def _resolve_faction(self, name: str, entity_type: Optional[str]) -> str:
        """阵营归纳: 密档 > 实体类型推断 > 兜底"""
        lore = CHARACTER_LORE.get(name) or SUPPLEMENTARY_LORE.get(name)
        if lore and lore.get("faction"):
            return lore["faction"]
        if (entity_type or "").lower() in ("place", "faction", "location", "organization", "org"):
            return "places_org"
        return "fan_manor"

    def _build_node(self, name: str, entity_type: Optional[str] = None,
                    desc: Optional[str] = None, aliases: Optional[List[str]] = None) -> Dict[str, Any]:
        lore = CHARACTER_LORE.get(name) or SUPPLEMENTARY_LORE.get(name) or {}
        faction = self._resolve_faction(name, entity_type)
        faction_meta = FACTIONS.get(faction, {})
        return {
            "id": name,
            "name": name,
            "type": (entity_type or lore.get("type") or ("Character" if name not in FACTIONS else "Faction")),
            "faction": faction,
            "faction_name": faction_meta.get("name", "其他"),
            "color": faction_meta.get("color", "#d4af37"),
            "badge": faction_meta.get("badge", "原著"),
            "title": lore.get("title", f"《庆余年》重要{entity_type or '角色'}"),
            "glyph": lore.get("avatar_glyph", name[:1]),
            "salience": lore.get("salience", 5),
            "description": lore.get("summary") or desc or f"《庆余年》中的{name}",
            "aliases": lore.get("aliases", aliases or [])
        }

    # ---------------- 全量图谱构建 ----------------

    def get_full_graph(self) -> Dict[str, Any]:
        """
        获取用于 SVG 渲染的全量图谱节点与连线数据 (带缓存)
        """
        core_path = os.path.join(os.path.dirname(__file__), "data", "graph", "core_relations.json")
        try:
            core_mtime = os.path.getmtime(core_path) if os.path.exists(core_path) else 0.0
        except OSError:
            core_mtime = 0.0
        now = time.time()
        if (self._graph_cache is not None
                and now - self._cache_time < GRAPH_CACHE_TTL
                and core_mtime == self._cache_core_mtime):
            return self._graph_cache

        # ---------- 1. 收集原始节点与连线 (core_relations 优先: 证据更丰富) ----------
        raw_nodes: Dict[str, Dict[str, Any]] = {}
        raw_links: List[Dict[str, Any]] = []

        core_data = []
        if os.path.exists(core_path):
            try:
                with open(core_path, "r", encoding="utf-8") as f:
                    core_data = json.load(f)
            except Exception as e:
                print(f"[GraphProvider] core_relations 读取错误: {e}")

        for item in core_data:
            src = self._normalize_name(item.get("source_name", ""))
            dst = self._normalize_name(item.get("target_name", ""))
            rel_type = item.get("type", "RELATED_TO")
            if not src or not dst or src == dst:
                continue
            for n in (src, dst):
                if n not in raw_nodes:
                    raw_nodes[n] = {}
            raw_links.append({
                "source": src, "target": dst, "type": rel_type,
                "chapter": item.get("chapter_title", ""),
                "evidence": item.get("evidence", "")
            })

        if self.driver:
            try:
                with self.driver.session() as session:
                    cypher_nodes = """
                    MATCH (n:Entity)
                    RETURN n.name as name, n.type as type,
                           n.description as desc, n.aliases as aliases
                    """
                    for r in session.run(cypher_nodes).data():
                        name = self._normalize_name(r.get("name"))
                        if not name or name in raw_nodes:
                            continue
                        raw_nodes[name] = {
                            "type": r.get("type"),
                            "desc": r.get("desc"),
                            "aliases": r.get("aliases")
                        }
                    cypher_rels = """
                    MATCH (s:Entity)-[r]->(t:Entity)
                    WHERE s.name IS NOT NULL AND t.name IS NOT NULL
                    RETURN s.name as src, type(r) as rel, t.name as dst
                    """
                    for r in session.run(cypher_rels).data():
                        src = self._normalize_name(r["src"])
                        dst = self._normalize_name(r["dst"])
                        if not src or not dst or src == dst:
                            continue
                        raw_links.append({"source": src, "target": dst, "type": r["rel"]})
            except Exception as e:
                print(f"[GraphProvider] Neo4j 读取出错: {e}")

        # ---------- 2. 节点清洗: 归并已做, 剔除杂讯与超长名 ----------
        nodes_dict: Dict[str, Dict[str, Any]] = {}
        for name, meta in raw_nodes.items():
            if self._is_junk(name) or len(name) > 12:
                continue
            nodes_dict[name] = self._build_node(
                name,
                entity_type=meta.get("type"),
                desc=meta.get("desc"),
                aliases=meta.get("aliases")
            )

        # ---------- 3. 连线清洗: 去自环/去无效端点/按三元组去重并累计权重 ----------
        dedup_links: Dict[tuple, Dict[str, Any]] = {}
        for l in raw_links:
            src, dst = self._normalize_name(l["source"]), self._normalize_name(l["target"])
            rel_type = l["type"]
            if src == dst or self._is_junk(src) or self._is_junk(dst):
                continue
            if (src, rel_type, dst) in WRONG_TRIPLES:
                continue  # 与原著明显不符的抽取错误
            if src not in nodes_dict or dst not in nodes_dict:
                continue
            key = (src, dst, rel_type)
            if key in dedup_links:
                dedup_links[key]["weight"] += 1
                continue
            rel_meta = RELATION_MAP.get(rel_type, {"label": rel_type, "color": "#cbd5e1", "dash": ""})
            dedup_links[key] = {
                "source": src, "target": dst, "type": rel_type,
                "label": rel_meta["label"], "color": rel_meta["color"],
                "dash": rel_meta.get("dash", ""),
                "weight": 1,
                "chapter": l.get("chapter", ""),
                "evidence": l.get("evidence") or f"原著知识图谱收录三元组: {src} -[{rel_meta['label']}]-> {dst}"
            }
        links_list = list(dedup_links.values())

        # ---------- 4. 确保密档人物必然在图 (最精致的核心节点) ----------
        for name in list(CHARACTER_LORE.keys()) + list(SUPPLEMENTARY_LORE.keys()):
            if name not in nodes_dict:
                nodes_dict[name] = self._build_node(name)

        # ---------- 5. 核心血缘与守护纽带兜底 (底层数据缺失时保底) ----------
        canon_fallback_links = [
            ("叶轻眉", "范闲", "MOTHER_OF", "生母", "叶轻眉产下范闲于太平别院"),
            ("庆帝", "范闲", "FATHER_OF", "生父", "庆帝乃范闲真正生父，身负霸道真气"),
            ("范建", "范闲", "FATHER_OF", "养父/义父", "以己子换范闲生路，护至澹州"),
            ("五竹", "范闲", "PROTECTS", "誓死守护", "受命于叶轻眉，守护少爷范闲一生"),
            ("五竹", "叶轻眉", "SERVES", "忠心侍奉", "自神庙随小姐走出，不离不弃"),
            ("陈萍萍", "叶轻眉", "SERVES", "终生敬仰", "视叶轻眉为人间唯一神明与信仰"),
            ("陈萍萍", "范闲", "PROTECTS", "暗中庇佑", "调黑骑、授提司腰牌，全力护其周全"),
            ("陈萍萍", "庆帝", "ENEMY_OF", "决死复仇", "为替叶轻眉复仇，藏枪轮椅孤身进宫"),
            ("庆帝", "叶轻眉", "KILLS", "设局害死", "假借太后与神庙之手将叶轻眉除于别院"),
            ("林婉儿", "范闲", "SPOUSE_OF", "结发夫妻", "庆庙初遇，定情鸡腿姑娘"),
            ("长公主", "林婉儿", "MOTHER_OF", "生母", "生下林婉儿，寄养于宫中"),
            ("林若甫", "林婉儿", "FATHER_OF", "生父", "宰相私生女，寄养林府"),
            ("庆帝", "长公主", "SIBLING_OF", "胞兄妹", "皇室兄妹，暗流涌动"),
            ("皇太后", "长公主", "MOTHER_OF", "母女", "长公主为太后亲生女儿"),
            ("庆帝", "靖郡王", "SIBLING_OF", "皇室兄弟", "立志做富贵闲王的胞弟"),
            ("长公主", "太子", "ALLIED_WITH", "暗中操纵", "深宫私情与政治同盟"),
            ("长公主", "二皇子", "ALLIED_WITH", "政治同盟", "借内库钱财扶持二皇子抗衡范闲"),
            ("费介", "范闲", "MASTER_OF", "恩师传道", "监察院三处主办，传授范闲毒经与解法"),
            ("范闲", "范若若", "SIBLING_OF", "兄妹情笃", "教导若若医理与巴雷特重狙"),
            ("范若若", "范思辙", "SIBLING_OF", "姐弟", "日常以戒尺管教范思辙"),
            ("范建", "柳氏", "SPOUSE_OF", "范府主母", "续弦主母柳氏，掌范府中馈"),
            ("柳氏", "范思辙", "MOTHER_OF", "生母", "范思辙生母"),
            ("范闲", "范思辙", "SIBLING_OF", "兄弟", "同府兄弟，一个善权谋一个善算账"),
            ("范建", "范思辙", "FATHER_OF", "父子", "范府二少爷"),
            ("范建", "范若若", "FATHER_OF", "父女", "范建亡妻所留独女"),
            ("叶重", "叶灵儿", "FATHER_OF", "父女", "将门虎女"),
            ("林婉儿", "叶灵儿", "FRIEND_OF", "闺中密友", "婉儿与灵儿自幼交好"),
            ("范闲", "王启年", "LEADS", "主仆心腹", "王启年为范闲头号得力干将"),
            ("范闲", "藤子京", "FRIEND_OF", "生死之交", "牛栏街刺杀中负伤犹自护主"),
            ("海棠朵朵", "范闲", "FRIEND_OF", "红颜知己", "北齐并肩作战，心意相通"),
            ("苦荷", "海棠朵朵", "MASTER_OF", "关门恩师", "授其天一道自然法门"),
            ("苦荷", "叶轻眉", "SERVES", "传法恩人", "当年神庙外得叶轻眉指点大宗师心法"),
            ("四顾剑", "叶轻眉", "SERVES", "点化恩人", "受叶轻眉赠剑谱而悟极剑"),
            ("叶流云", "五竹", "ENEMY_OF", "因果武道", "曾被五竹铁钎痛揍后顿悟流云散手"),
            ("范闲", "监察院", "LEADS", "提司执掌", "身怀监察院提司腰牌，可号令八处"),
            ("范闲", "内库", "LEADS", "掌管商号", "收复母亲遗留之天下最大财富工坊"),
            ("陈萍萍", "黑骑", "LEADS", "执掌黑骑", "玄甲黑骑为监察院最锋利之刀"),
            ("范建", "户部", "LEADS", "执掌户部", "司南伯执掌天下钱粮"),
            ("范闲", "澹州", "LOCATED_IN", "幼年成长地", "自幼寄居澹州奶奶家中长大"),
            ("老夫人", "澹州", "LOCATED_IN", "常居澹州", "常年留守澹州范府老家"),
            ("海棠朵朵", "北齐", "BELONGS_TO", "北齐圣女", "天一道圣女, 北齐江湖代表"),
            ("苦荷", "北齐", "BELONGS_TO", "北齐国师", "一生庇护北齐国祚"),
            ("战豆豆", "北齐", "LEADS", "北齐皇帝", "少年天子君临北齐"),
            ("司理理", "北齐", "BELONGS_TO", "北齐密谍", "潜伏京都的北齐密谍"),
            ("肖恩", "北齐", "BELONGS_TO", "北齐密谍之祖", "北齐老牌密谍首领"),
            ("庄墨韩", "北齐", "BELONGS_TO", "北齐文宗", "天下文宗出身北齐"),
            ("庄墨韩", "范闲", "ENEMY_OF", "殿前构陷", "受胁迫于殿前以旧诗构陷范闲, 晚年托书释怨"),
            ("司理理", "长公主", "SERVES", "受其胁迫", "受长公主一系胁迫卷入牛栏街之谋"),
            ("司理理", "范闲", "ENEMY_OF", "追缉纠葛", "牛栏街案发后遭范闲追缉, 押送北齐途中化敌为友"),
            ("四顾剑", "东夷城", "GOVERNS", "一剑守一城", "以大宗师之威庇护东夷城"),
            ("叶轻眉", "神庙", "LOCATED_IN", "自神庙走出", "携五竹自极北神庙走入人间"),
            ("五竹", "神庙", "LOCATED_IN", "神庙出身", "神庙遗留的仿生战斗机器人"),
            ("苦荷", "神庙", "LOCATED_IN", "赴庙求道", "当年与肖恩远赴神庙得授天一道")
        ]
        for src, dst, r_type, r_lbl, ev in canon_fallback_links:
            if self._is_junk(src) or self._is_junk(dst):
                continue
            for n in (src, dst):
                if n not in nodes_dict:
                    nodes_dict[n] = self._build_node(n)
            key = (src, dst, r_type)
            if key in dedup_links:
                continue
            rm = RELATION_MAP.get(r_type, {"label": r_lbl, "color": "#ef4444", "dash": ""})
            link = {
                "source": src, "target": dst, "type": r_type,
                "label": r_lbl or rm["label"], "color": rm["color"],
                "dash": rm.get("dash", ""), "weight": 1, "evidence": ev
            }
            links_list.append(link)
            dedup_links[key] = link

        # ---------- 6. 度数统计 + 剔除孤立杂讯节点 ----------
        node_degree: Dict[str, int] = {}
        for l in links_list:
            node_degree[l["source"]] = node_degree.get(l["source"], 0) + 1
            node_degree[l["target"]] = node_degree.get(l["target"], 0) + 1

        curated = set(CHARACTER_LORE.keys()) | set(SUPPLEMENTARY_LORE.keys())
        nodes_list = []
        for n_id, n_data in nodes_dict.items():
            deg = node_degree.get(n_id, 0)
            if deg == 0 and n_id not in curated:
                continue  # 未收录密档且无任何连线的孤立节点不入图
            salience = n_data.get("salience", 5)
            n_data["degree"] = deg
            n_data["size"] = max(26, min(50, 20 + deg * 2 + salience * 2))
            nodes_list.append(n_data)

        # ---------- 7. 输出并缓存 ----------
        result = {
            "factions": list(FACTIONS.values()),
            "nodes": nodes_list,
            "links": links_list,
            "stats": {
                "total_nodes": len(nodes_list),
                "total_links": len(links_list),
                "total_factions": len(FACTIONS)
            }
        }
        self._graph_cache = result
        self._cache_time = now
        self._cache_core_mtime = core_mtime
        return result

    def get_character_detail(self, name: str) -> Optional[Dict[str, Any]]:
        """
        获取单个角色的深度秘卷详情、全向关系网与原著考据
        """
        canon_name = self._normalize_name(name)
        graph = self.get_full_graph()

        target_node = None
        for n in graph["nodes"]:
            if n["name"] == canon_name:
                target_node = n
                break

        if not target_node:
            return None

        # 查找相关连线
        related_links = []
        for l in graph["links"]:
            if l["source"] == canon_name:
                related_links.append({
                    "direction": "out",
                    "target": l["target"],
                    "label": l["label"],
                    "color": l["color"],
                    "evidence": l.get("evidence", ""),
                    "chapter": l.get("chapter", "")
                })
            elif l["target"] == canon_name:
                related_links.append({
                    "direction": "in",
                    "target": l["source"],
                    "label": l["label"],
                    "color": l["color"],
                    "evidence": l.get("evidence", ""),
                    "chapter": l.get("chapter", "")
                })

        lore = CHARACTER_LORE.get(canon_name) or SUPPLEMENTARY_LORE.get(canon_name) or {}
        quotes = lore.get("quotes", [])

        # 生成 3 个预设专属问题
        questions = [
            f"探询「{canon_name}」在《庆余年》全书中的身世与真正立场？",
            f"「{canon_name}」与哪些关键人物结有最深沉的羁绊或仇怨？",
            f"原著小说中，「{canon_name}」最终迎来了怎样的结局？"
        ]
        if canon_name == "范闲":
            questions = [
                "范闲的身世之谜：生父庆帝与生母叶轻眉当年发生了什么？",
                "五竹与范闲之间究竟是何种超越生死的主仆与守护关系？",
                "范闲最后如何与大宗师庆帝决战，结局如何？"
            ]
        elif canon_name == "五竹":
            questions = [
                "五竹为什么一直戴着黑布蒙眼？眼罩下到底藏着什么？",
                "五竹与极北神庙是什么渊源？他为何能长生不老？",
                "大东山与皇宫终局一战中，五竹展现了怎样的真正威力？"
            ]
        elif canon_name == "陈萍萍":
            questions = [
                "陈萍萍为何执意刺杀庆帝？他为叶轻眉复仇的计划如何进行？",
                "陈萍萍的轮椅里到底藏着什么样的绝密暗器？",
                "陈萍萍临终前与庆帝对话的“那箱子是什么”，庆帝如何回应？"
            ]
        elif canon_name == "庆帝":
            questions = [
                "庆帝既然深爱叶轻眉，为何最终非要设局害死她？",
                "庆帝是如何练成霸道真气并隐藏大宗师身份数十年的？",
                "庆帝对范闲这个儿子到底是利用多于父爱，还是兼而有之？"
            ]
        elif canon_name == "叶轻眉":
            questions = [
                "叶轻眉当年从神庙走出时究竟带来了哪些现代科技遗物？",
                "叶轻眉在监察院前立的石碑上写了什么震撼天下的话？",
                "叶轻眉在庆国建立内库与监察院的初衷是什么？"
            ]

        return {
            "node": target_node,
            "relations": related_links,
            "lore": lore,
            "quotes": quotes,
            "suggested_questions": questions
        }


# 全局单例
graph_provider = NovelGraphProvider()
