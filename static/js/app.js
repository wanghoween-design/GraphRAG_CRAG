/**
 * 《庆余年》卷帙秘档 · 智能考据阁前端控制器 (App Controller)
 * 职责：
 * - 协调 SVG 关系图谱与 CRAG 智能问答交互
 * - 渲染 CRAG 检索推演全链路过程 (Retrieve-Grade-Recover)
 * - 联动人物秘卷卡片与一键探询锦囊
 * - 视图切换与全局状态同步
 */

// 预置高信度离线图谱数据 (保障在任何无网络或离线场景下永不白屏)
const FALLBACK_GRAPH_DATA = {
  factions: [
    { id: "fan_manor", name: "范府世家", color: "#f59e0b", badge: "范府" },
    { id: "imperial", name: "南庆皇廷", color: "#ef4444", badge: "皇廷" },
    { id: "council", name: "监察暗网", color: "#8b5cf6", badge: "监察院" },
    { id: "grandmaster", name: "世外宗师与神庙", color: "#10b981", badge: "宗师/神庙" },
    { id: "beiqi_romance", name: "红颜与江湖", color: "#06b6d4", badge: "红颜/江湖" }
  ],
  nodes: [
    { id: "范闲", name: "范闲", faction: "fan_manor", faction_name: "范府世家", color: "#f59e0b", badge: "提司/主角", glyph: "闲", salience: 10, size: 46, title: "监察院提司 · 穿越天脉者", description: "《庆余年》主角，叶轻眉与庆帝之子，户部尚书范建养子，执掌内库与监察院。" },
    { id: "叶轻眉", name: "叶轻眉", faction: "grandmaster", faction_name: "世外宗师", color: "#10b981", badge: "神庙仙女", glyph: "眉", salience: 10, size: 44, title: "现代工科女性 · 时代启蒙者", description: "从极北神庙携五竹与重狙南下，助庆帝登基，创办内库与监察院，全书灵魂源头。" },
    { id: "庆帝", name: "庆帝", faction: "imperial", faction_name: "南庆皇廷", color: "#ef4444", badge: "王道至尊", glyph: "庆", salience: 10, size: 44, title: "南庆天子 · 隐藏大宗师", description: "范闲真正生父，深谙权谋制衡的大宗师，当年借太后与神庙之手除死叶轻眉。" },
    { id: "五竹", name: "五竹", faction: "grandmaster", faction_name: "神庙守护", color: "#10b981", badge: "守护神", glyph: "竹", salience: 10, size: 44, title: "仿生战斗机器人 · 终身守护者", description: "神庙高科技超合金仿生人，黑布覆双眸(内藏高能激光)，手持黑钎，终身庇护少爷范闲。" },
    { id: "陈萍萍", name: "陈萍萍", faction: "council", faction_name: "监察暗网", color: "#8b5cf6", badge: "特务之王", glyph: "萍", salience: 10, size: 44, title: "监察院第一任院长 · 轮椅之枭", description: "双腿残疾乘精钢轮椅，一生只忠敬叶轻眉，布下二十载大局，藏枪轮椅孤身刺杀庆帝。" },
    { id: "范建", name: "范建", faction: "fan_manor", faction_name: "范府世家", color: "#f59e0b", badge: "户部尚书", glyph: "建", salience: 8, size: 36, title: "司南伯爵 · 范闲养父", description: "以亲子之死救下范闲，执掌户部与虎卫，视范闲如己出。" },
    { id: "林婉儿", name: "林婉儿", faction: "beiqi_romance", faction_name: "红颜", color: "#06b6d4", badge: "鸡腿姑娘", glyph: "婉", salience: 8, size: 36, title: "晨郡主 · 范闲结发之妻", description: "长公主李云睿与林若甫之女，庆庙鸡腿结缘，范闲一生挚爱与温柔港湾。" },
    { id: "范若若", name: "范若若", faction: "fan_manor", faction_name: "范府世家", color: "#f59e0b", badge: "第一才女", glyph: "若", salience: 7, size: 32, title: "范闲之妹 · 重狙传人", description: "京都第一才女，对哥哥范闲极其信赖与崇敬，后得传巴雷特狙击枪。" },
    { id: "长公主", name: "长公主", faction: "imperial", faction_name: "南庆皇廷", color: "#ef4444", badge: "内库掌权", glyph: "睿", salience: 8, size: 36, title: "李云睿 · 倾城阴谋家", description: "庆帝胞妹，婉儿生母，心机狠辣偏执，暗结太子与二皇子。" },
    { id: "费介", name: "费介", faction: "council", faction_name: "监察暗网", color: "#8b5cf6", badge: "毒宗之首", glyph: "介", salience: 7, size: 32, title: "监察院三处主办 · 范闲启蒙师", description: "天下第一用毒大师，极度护犊，传授幼年范闲医术与毒术。" },
    { id: "王启年", name: "王启年", faction: "council", faction_name: "监察暗网", color: "#8b5cf6", badge: "神行心腹", glyph: "王", salience: 7, size: 32, title: "监察院一处文书 · 轻功通神", description: "虽贪财惧内却重诺忠勇，为范闲身边最贴心敏捷之头号干将。" },
    { id: "海棠朵朵", name: "海棠朵朵", faction: "beiqi_romance", faction_name: "红颜知己", color: "#06b6d4", badge: "北齐圣女", glyph: "棠", salience: 7, size: 34, title: "天一道圣女 · 苦荷关门弟子", description: "九品上超凡高手，布衣赤脚，与范闲相知相惜之红颜至交。" },
    { id: "苦荷", name: "苦荷", faction: "grandmaster", faction_name: "世外宗师", color: "#10b981", badge: "北齐国师", glyph: "苦", salience: 8, size: 36, title: "四大宗师 · 天一道创祖", description: "早年得叶轻眉指点天一道功法破入宗师，庇佑北齐国祚。" },
    { id: "四顾剑", name: "四顾剑", faction: "grandmaster", faction_name: "世外宗师", color: "#10b981", badge: "东夷剑痴", glyph: "剑", salience: 8, size: 36, title: "四大宗师 · 绝剑一城", description: "东夷城城主，受叶轻眉赠剑谱顿悟唯我一剑，以剑守一城。" }
  ],
  links: [
    { source: "叶轻眉", target: "范闲", label: "生母", color: "#ef4444", evidence: "叶轻眉于太平别院诞下范闲" },
    { source: "庆帝", target: "范闲", label: "生父", color: "#f59e0b", evidence: "范闲乃庆帝与叶轻眉真正骨肉" },
    { source: "范建", target: "范闲", label: "养父/义父", color: "#f59e0b", evidence: "以亲子替死保全范闲送至澹州" },
    { source: "五竹", target: "范闲", label: "誓死守护", color: "#10b981", evidence: "受命于叶轻眉，一生护少爷周全" },
    { source: "五竹", target: "叶轻眉", label: "忠心侍奉", color: "#06b6d4", evidence: "自极北神庙追随小姐降临凡尘" },
    { source: "陈萍萍", target: "叶轻眉", label: "终生敬仰", color: "#8b5cf6", evidence: "视叶轻眉为人间唯一明灯与知己" },
    { source: "陈萍萍", target: "范闲", label: "暗中庇佑", color: "#8b5cf6", evidence: "调黑骑、赠提司腰牌，倾尽院务护其成长" },
    { source: "陈萍萍", target: "庆帝", label: "决死复仇", color: "#dc2626", evidence: "为替叶轻眉复仇，藏枪轮椅孤身进宫决死一搏" },
    { source: "庆帝", target: "叶轻眉", label: "设局害死", color: "#b91c1c", evidence: "调开各方护卫借太后贵族之手血洗别院" },
    { source: "林婉儿", target: "范闲", label: "结发夫妻", color: "#f43f5e", evidence: "庆庙初遇鸡腿定情，结为良缘" },
    { source: "长公主", target: "林婉儿", label: "生母", color: "#ef4444", evidence: "长公主李云睿与宰相林若甫之女" },
    { source: "庆帝", target: "长公主", label: "皇室兄妹", color: "#ef4444", evidence: "皇室兄妹，内库与宫权错综交织" },
    { source: "费介", target: "范闲", label: "授业恩师", color: "#14b8a6", evidence: "监察院三处主办，授以毒道与解法" },
    { source: "范闲", target: "范若若", label: "兄妹情笃", color: "#ec4899", evidence: "传授现代医术与巴雷特狙击重法" },
    { source: "范闲", target: "王启年", label: "主仆心腹", color: "#8b5cf6", evidence: "神行百里，随范闲北上搏命" },
    { source: "海棠朵朵", target: "范闲", label: "红颜知己", color: "#06b6d4", evidence: "北齐相识相伴，洒脱自然" },
    { source: "苦荷", target: "海棠朵朵", label: "恩师传道", color: "#10b981", evidence: "苦荷关门真传弟子" },
    { source: "苦荷", target: "叶轻眉", label: "受恩点化", color: "#10b981", evidence: "神庙门前受赠天一道真经而成宗师" },
    { source: "四顾剑", target: "叶轻眉", label: "受恩悟道", color: "#10b981", evidence: "大树下得赠剑谱，终成天下第一杀伐剑圣" }
  ]
};

document.addEventListener("DOMContentLoaded", () => {
  // 初始化全局实例
  window.novelApp = new NovelApp();
});

class NovelApp {
  constructor() {
    this.graphEngine = null;
    this.currentSessionId = "session_" + Date.now();
    this.isQuerying = false;

    this.initGraph();
    this.initUIEvents();
    this.fetchSystemStatus();
  }

  /**
   * 初始化 SVG 关系图谱
   */
  initGraph() {
    this.graphEngine = new NovelGraphEngine("novel-graph-svg", {
      onNodeClick: (node) => this.showCharacterDossier(node),
      onDataLoaded: (data) => {
        const nEl = document.getElementById("stat-nodes");
        const lEl = document.getElementById("stat-links");
        if (nEl) nEl.textContent = data.nodes ? data.nodes.length : "--";
        if (lEl) lEl.textContent = data.links ? data.links.length : "--";
        this.updateDensityLabels();
      }
    });

    // 优先从后端拉取完整 Neo4j 图谱数据
    fetch("/api/graph")
      .then(res => {
        if (!res.ok) throw new Error("API not ready");
        return res.json();
      })
      .then(data => {
        console.log("[NovelApp] 成功载入 Neo4j 实时图谱数据:", data.stats);
        this.graphEngine.loadData(data);
      })
      .catch(err => {
        console.warn("[NovelApp] 使用预置原著图谱数据渲染:", err);
        this.graphEngine.loadData(FALLBACK_GRAPH_DATA);
      });
  }

  /**
   * 初始化界面交互事件
   */
  initUIEvents() {
    // 1. 视图切换
    const workspace = document.getElementById("workspace");
    const btnSplit = document.getElementById("btn-view-split");
    const btnGraph = document.getElementById("btn-view-graph");
    const btnChat = document.getElementById("btn-view-chat");

    const setView = (mode) => {
      workspace.className = "workspace-container " + mode;
      [btnSplit, btnGraph, btnChat].forEach(b => b.classList.remove("active"));
      if (mode === "") btnSplit.classList.add("active");
      else if (mode === "mode-graph-only") btnGraph.classList.add("active");
      else if (mode === "mode-chat-only") btnChat.classList.add("active");

      // 视口变动重新居中图谱
      setTimeout(() => this.graphEngine && this.graphEngine.centerView(), 300);
    };

    btnSplit.addEventListener("click", () => setView(""));
    btnGraph.addEventListener("click", () => setView("mode-graph-only"));
    btnChat.addEventListener("click", () => setView("mode-chat-only"));

    // 2. 画布控制把手
    document.getElementById("ctrl-zoom-in").addEventListener("click", () => {
      this.graphEngine.transform.scale = Math.min(3.5, this.graphEngine.transform.scale * 1.25);
      this.graphEngine.applyTransform();
    });
    document.getElementById("ctrl-zoom-out").addEventListener("click", () => {
      this.graphEngine.transform.scale = Math.max(0.2, this.graphEngine.transform.scale * 0.8);
      this.graphEngine.applyTransform();
    });
    document.getElementById("ctrl-reset-view").addEventListener("click", () => {
      this.graphEngine.centerView();
      this.graphEngine.clearHighlight();
      this.hideCharacterDossier();
    });
    document.getElementById("ctrl-toggle-sim").addEventListener("click", (e) => {
      const isRunning = this.graphEngine.toggleSimulation();
      e.currentTarget.style.color = isRunning ? "var(--color-gold)" : "var(--text-muted)";
    });

    // 3. 呈现密度控制 (核心22人 vs 全景96人)
    const btnDensityCore = document.getElementById("btn-density-core");
    const btnDensityAll = document.getElementById("btn-density-all");
    if (btnDensityCore && btnDensityAll) {
      btnDensityCore.addEventListener("click", () => {
        btnDensityCore.classList.add("active");
        btnDensityAll.classList.remove("active");
        this.graphEngine.setDensityMode("core");
      });
      btnDensityAll.addEventListener("click", () => {
        btnDensityAll.classList.add("active");
        btnDensityCore.classList.remove("active");
        this.graphEngine.setDensityMode("all");
      });
    }

    // 4. 连线关系文字显隐切换 (智能聚焦 vs 常驻显示)
    const btnToggleLabels = document.getElementById("btn-toggle-labels");
    if (btnToggleLabels) {
      btnToggleLabels.addEventListener("click", () => {
        if (this.graphEngine.labelMode === "smart") {
          this.graphEngine.labelMode = "always";
          btnToggleLabels.innerHTML = "🏷️ 常驻显示铭文";
          btnToggleLabels.style.color = "var(--text-primary)";
        } else {
          this.graphEngine.labelMode = "smart";
          btnToggleLabels.innerHTML = "🏷️ 智能聚焦铭文";
          btnToggleLabels.style.color = "var(--color-gold)";
        }
        this.graphEngine.renderDOM();
      });
    }

    // 5. 阵营筛选分类
    const factionTabs = document.getElementById("faction-tabs");
    factionTabs.addEventListener("click", (e) => {
      const target = e.target.closest(".tab-chip");
      if (!target) return;
      factionTabs.querySelectorAll(".tab-chip").forEach(t => t.classList.remove("active"));
      target.classList.add("active");
      const faction = target.getAttribute("data-faction");
      this.graphEngine.setFactionFilter(faction);
    });

    // 6. 人物实时检索框
    const searchInput = document.getElementById("character-search");
    const clearSearchBtn = document.getElementById("search-clear-btn");

    searchInput.addEventListener("input", (e) => {
      const val = e.target.value.trim();
      clearSearchBtn.style.display = val ? "block" : "none";
      if (val) {
        this.graphEngine.focusCharacter(val);
      } else {
        this.graphEngine.clearHighlight();
      }
    });
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = searchInput.value.trim();
        if (val) this.graphEngine.focusCharacter(val);
      }
    });
    clearSearchBtn.addEventListener("click", () => {
      searchInput.value = "";
      clearSearchBtn.style.display = "none";
      this.graphEngine.clearHighlight();
    });

    // 5. 秘卷抽屉关闭按钮
    document.getElementById("dossier-close-btn").addEventListener("click", () => {
      this.hideCharacterDossier();
    });

    // 6. 快捷经典提问推荐条
    document.querySelectorAll(".preset-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const prompt = chip.getAttribute("data-prompt");
        this.sendUserQuestion(prompt);
      });
    });

    // 7. 聊天输入框与发送按钮
    const textarea = document.getElementById("chat-textarea");
    const sendBtn = document.getElementById("send-message-btn");

    const doSend = () => {
      const q = textarea.value.trim();
      if (!q || this.isQuerying) return;
      textarea.value = "";
      textarea.style.height = "auto";
      this.sendUserQuestion(q);
    };

    sendBtn.addEventListener("click", doSend);
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        doSend();
      }
    });

    // 8. 清空聊天
    document.getElementById("clear-chat-btn").addEventListener("click", () => {
      const container = document.getElementById("chat-messages");
      container.innerHTML = `
        <div class="chat-message-row agent-row">
          <div class="message-avatar">阁</div>
          <div class="message-bubble-wrapper">
            <div class="message-sender">考据掌阁学士 · CRAG Agent</div>
            <div class="message-bubble agent-bubble">
              <p>论道长卷已重展，尊客可随时垂询《庆余年》中任意人物渊源与暗潮交织。</p>
            </div>
          </div>
        </div>
      `;
    });
  }

  /**
   * 调取后端状态 (如实反映 Neo4j 与 CRAG 引擎模式)
   */
  fetchSystemStatus() {
    fetch("/api/status")
      .then(res => res.json())
      .then(status => {
        const chip = document.getElementById("neo4j-chip");
        if (status.neo4j_connected) {
          chip.innerHTML = `
            <span class="pulse-dot green"></span>
            <span class="chip-text">Neo4j 图谱已载入 (<span id="stat-nodes">${status.total_nodes}</span> 实体 / <span id="stat-links">${status.total_links}</span> 纽带)</span>
          `;
        } else {
          chip.innerHTML = `
            <span class="pulse-dot red"></span>
            <span class="chip-text">Neo4j 离线 · 本地典藏图谱 (<span id="stat-nodes">${status.total_nodes}</span> 实体 / <span id="stat-links">${status.total_links}</span> 纽带)</span>
          `;
        }
        const cragChip = document.getElementById("crag-chip");
        if (cragChip && status.crag_engine) {
          cragChip.innerHTML = `
            <span class="pulse-dot ${status.ollama_active ? "green" : "amber"}"></span>
            <span class="chip-text">${status.crag_engine}</span>
          `;
        }
      })
      .catch(() => {
        const chip = document.getElementById("neo4j-chip");
        if (chip) {
          chip.innerHTML = `
            <span class="pulse-dot red"></span>
            <span class="chip-text">后端服务未连接</span>
          `;
        }
      });
  }

  /**
   * 依据实际载入的数据量刷新密度切换按钮的人数标注
   */
  updateDensityLabels() {
    const btnCore = document.getElementById("btn-density-core");
    const btnAll = document.getElementById("btn-density-all");
    if (!this.graphEngine || !this.graphEngine.allNodes) return;
    const coreCount = this.graphEngine.allNodes.filter(n => n.isCore).length;
    const allCount = this.graphEngine.allNodes.length;
    if (btnCore) {
      btnCore.innerHTML = `🌟 宗师核心 (${coreCount}人)`;
      btnCore.title = `仅展示 ${coreCount} 位核心主角与高关联人物，清雅开阔`;
    }
    if (btnAll) {
      btnAll.innerHTML = `🌌 原著全景 (${allCount}人)`;
      btnAll.title = `展开 ${allCount} 位原著全量人物与势力，探索宏大脉络`;
    }
  }

  /**
   * 展开人物秘档抽屉
   */
  showCharacterDossier(node) {
    const drawer = document.getElementById("character-dossier");
    drawer.classList.add("active");

    // 基础信息
    document.getElementById("dossier-avatar").textContent = node.glyph || node.name.slice(0, 1);
    document.getElementById("dossier-avatar").style.borderColor = node.color || "#d4af37";
    document.getElementById("dossier-name").textContent = node.name;
    document.getElementById("dossier-badge").textContent = node.badge || node.faction_name || "原著";
    document.getElementById("dossier-role").textContent = node.title || `《庆余年》重要人物`;
    document.getElementById("dossier-aliases").textContent = (node.aliases && node.aliases.length) 
      ? `名号别称：${node.aliases.join("、")}` 
      : `名号别称：${node.name}`;

    document.getElementById("dossier-summary").textContent = node.description || "原著关键登场人物，与诸方权贵及隐世势力有着千丝万缕之勾连。";

    // 异步拉取后端丰富细节 (Quotes、Relations矩阵、Suggested Prompts)
    fetch(`/api/character/${encodeURIComponent(node.name)}`)
      .then(res => res.json())
      .then(detail => {
        // 经典语录
        if (detail.quotes && detail.quotes.length) {
          document.getElementById("dossier-quote").textContent = detail.quotes[0];
          document.getElementById("dossier-quote").style.display = "";
        } else {
          document.getElementById("dossier-quote").style.display = "none";
        }

        // 关系网络矩阵
        const relContainer = document.getElementById("dossier-relations");
        relContainer.innerHTML = "";
        const rels = detail.relations || [];
        document.getElementById("dossier-rel-count").textContent = rels.length;

        rels.slice(0, 12).forEach(r => {
          const tag = document.createElement("div");
          tag.className = "rel-tag";
          tag.innerHTML = `
            <span class="rel-tag-label" style="color: ${r.color};">${r.label}:</span>
            <span>${r.target}</span>
            <span style="font-size: 10px; opacity: 0.6;">↗</span>
          `;
          tag.addEventListener("click", () => {
            this.graphEngine.focusCharacter(r.target);
          });
          relContainer.appendChild(tag);
        });

        // 专属推荐提问
        const promptContainer = document.getElementById("dossier-suggested-prompts");
        promptContainer.innerHTML = "";
        const questions = detail.suggested_questions || [
          `探问「${node.name}」在全书中的核心立场与身世？`,
          `「${node.name}」与范闲之间有什么不可调和的矛盾或因果？`
        ];
        questions.forEach(q => {
          const btn = document.createElement("button");
          btn.className = "suggest-prompt-btn";
          btn.innerHTML = `💡 ${q}`;
          btn.addEventListener("click", () => {
            this.sendUserQuestion(q);
          });
          promptContainer.appendChild(btn);
        });
      })
      .catch(() => {
        // Fallback: 本地依据现有图谱渲染
        const relContainer = document.getElementById("dossier-relations");
        relContainer.innerHTML = "";
        const relatedLinks = this.graphEngine.links.filter(l => l.source === node.name || l.target === node.name);
        document.getElementById("dossier-rel-count").textContent = relatedLinks.length;
        relatedLinks.slice(0, 8).forEach(l => {
          const other = l.source === node.name ? l.target : l.source;
          const tag = document.createElement("div");
          tag.className = "rel-tag";
          tag.innerHTML = `<span class="rel-tag-label" style="color: ${l.color};">${l.label}:</span> <span>${other}</span>`;
          tag.addEventListener("click", () => this.graphEngine.focusCharacter(other));
          relContainer.appendChild(tag);
        });
      });
  }

  hideCharacterDossier() {
    document.getElementById("character-dossier").classList.remove("active");
  }

  /**
   * 发送用户提问并执行 CRAG 推演流
   */
  sendUserQuestion(question) {
    if (this.isQuerying) return;
    this.isQuerying = true;

    // 1. 插入用户消息
    const messagesBox = document.getElementById("chat-messages");
    const userRow = document.createElement("div");
    userRow.className = "chat-message-row user-row";
    userRow.innerHTML = `
      <div class="message-avatar">客</div>
      <div class="message-bubble-wrapper">
        <div class="message-sender">研读者</div>
        <div class="message-bubble user-bubble">${this.escapeHtml(question)}</div>
      </div>
    `;
    messagesBox.appendChild(userRow);

    // 2. 插入 Agent 思考占位
    const agentRow = document.createElement("div");
    agentRow.className = "chat-message-row agent-row";
    const agentBubbleId = `bubble-${Date.now()}`;
    agentRow.innerHTML = `
      <div class="message-avatar">阁</div>
      <div class="message-bubble-wrapper">
        <div class="message-sender">考据掌阁学士 · CRAG Agent</div>
        <div class="message-bubble agent-bubble" id="${agentBubbleId}">
          <div style="display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-gold);">
            <span>翻阅《庆余年》卷帙并检索 Neo4j 实体中...</span>
            <div class="typing-dots"><span></span><span></span><span></span></div>
          </div>
        </div>
      </div>
    `;
    messagesBox.appendChild(agentRow);
    messagesBox.scrollTop = messagesBox.scrollHeight;

    // 联动：如果在问题中提及了人物名，自动在左侧图谱中高亮
    this.autoHighlightByQuery(question);

    // 3. 请求后端 API
    fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: question, session_id: this.currentSessionId })
    })
      .then(res => {
        if (!res.ok) throw new Error("服务端响应异常");
        return res.json();
      })
      .then(data => {
        this.renderAgentResponse(agentBubbleId, data);
      })
      .catch(err => {
        console.error("[NovelApp] Chat error:", err);
        // 本地离线智能推演
        this.renderOfflineResponse(agentBubbleId, question);
      })
      .finally(() => {
        this.isQuerying = false;
        messagesBox.scrollTop = messagesBox.scrollHeight;
      });
  }

  /**
   * 自动在图谱中聚焦提问中的角色
   */
  autoHighlightByQuery(text) {
    const knownNames = ["范闲", "叶轻眉", "庆帝", "五竹", "陈萍萍", "范建", "林婉儿", "长公主", "海棠朵朵", "王启年", "苦荷", "四顾剑"];
    for (const name of knownNames) {
      if (text.includes(name)) {
        this.graphEngine.focusCharacter(name);
        break;
      }
    }
  }

  /**
   * 渲染带有 CRAG 全流程推演折叠卡片的 Agent 回复
   */
  renderAgentResponse(bubbleId, data) {
    const bubble = document.getElementById(bubbleId);
    if (!bubble) return;

    const steps = data.steps || [];
    let cragTraceHtml = "";

    if (steps.length > 0) {
      const stepItems = steps.map((s, idx) => {
        if (s.node.includes("Memory")) {
          return `
            <div class="trace-step">
              <span class="trace-step-name">🧠 【步骤 1】意图与指代消解 (Memory Node)</span>
              <span class="trace-step-content">${s.description || '识别核心实体'}</span>
            </div>
          `;
        } else if (s.node.includes("Retrieve")) {
          const triplesList = (s.triples || []).map(t => `<li>${this.escapeHtml(t)}</li>`).join("");
          const chaptersList = (s.chapters || []).join("、");
          return `
            <div class="trace-step">
              <span class="trace-step-name">🕸️ 【步骤 2】知识图谱与全卷篇章双路召回 (Dual-Retriever)</span>
              <span class="trace-step-content">
                命中 <strong>${s.total_triples || 0}</strong> 条实体纽带：
                <ul class="triples-list">${triplesList}</ul>
                <div style="margin-top: 4px;"><strong>卷册定位：</strong> ${chaptersList}</div>
              </span>
            </div>
          `;
        } else if (s.node.includes("Grader")) {
          const pct = Math.round((s.confidence_score || 0.9) * 100);
          return `
            <div class="trace-step">
              <span class="trace-step-name">⚖️ 【步骤 3】CRAG 充分度评估与反思 (Grader Node)</span>
              <span class="trace-step-content">
                ${this.escapeHtml(s.reasoning || '证据链完整')}
                <div class="confidence-bar-wrap">
                  <span style="font-size: 11px;">证据置信度:</span>
                  <div class="confidence-bar"><div class="confidence-fill" style="width: ${pct}%;"></div></div>
                  <span class="confidence-score">${pct}% [${s.status || 'PASS'}]</span>
                </div>
              </span>
            </div>
          `;
        } else if (s.node.includes("Rewrite")) {
          return `
            <div class="trace-step">
              <span class="trace-step-name">✍️ 【步骤 4】提问自动改写 (Rewrite Node)</span>
              <span class="trace-step-content">改写后提问: <strong>${this.escapeHtml(s.rewritten_question || '')}</strong></span>
            </div>
          `;
        } else if (s.node.includes("Web Search")) {
          return `
            <div class="trace-step">
              <span class="trace-step-name">🌐 【步骤 4】Tavily 联网兜底 (Web Search Node)</span>
              <span class="trace-step-content">${this.escapeHtml(s.summary || '本地检索穷尽，已联网补充资料')}</span>
            </div>
          `;
        } else if (s.node.includes("Generate")) {
          return `
            <div class="trace-step">
              <span class="trace-step-name">📜 【终章】文学考据生成 (Synthesis Node)</span>
              <span class="trace-step-content">依据图谱三元组与原著篇章切片完成考据合成${s.model ? ` · 引擎: ${this.escapeHtml(s.model)}` : ''}。</span>
            </div>
          `;
        }
        return "";
      }).join("");

      cragTraceHtml = `
        <div class="crag-trace-card open">
          <div class="crag-trace-header" onclick="this.parentElement.classList.toggle('open')">
            <span class="crag-trace-title">
              <span>⚡</span> CRAG 考据推演全链路 (Retrieve-Grade-Recover)
            </span>
            <span class="crag-trace-toggle-icon">▼</span>
          </div>
          <div class="crag-trace-body">
            ${stepItems}
          </div>
        </div>
      `;
    }

    // 解析 Markdown 与人名互动标记
    const formattedAnswer = this.formatNovelAnswer(data.final_answer || "考据已完成。");

    bubble.innerHTML = `
      ${cragTraceHtml}
      <div class="markdown-content">
        ${formattedAnswer}
      </div>
    `;

    // 绑定答案中可点击的人名
    bubble.querySelectorAll(".char-link").forEach(link => {
      link.addEventListener("click", () => {
        const name = link.getAttribute("data-char");
        this.graphEngine.focusCharacter(name);
      });
    });
  }

  /**
   * 离线兜底考据回答
   */
  renderOfflineResponse(bubbleId, question) {
    const bubble = document.getElementById(bubbleId);
    if (!bubble) return;

    let ans = `在《庆余年》原著考据中，关于“${question}”的推演牵涉深宫权谋与昔年叶轻眉留下的深远因果。您可以点击左侧图谱中的核心人物节点，查看其专属的人事考据与羁绊网络。`;
    bubble.innerHTML = `<div class="markdown-content"><p>${ans}</p></div>`;
  }

  /**
   * 简单格式化 Markdown，并将已知小说人名转为可点击的交互标签
   */
  formatNovelAnswer(markdownText) {
    let html = markdownText
      .replace(/^### (.*$)/gim, '<h3>$1</h3>')
      .replace(/^#### (.*$)/gim, '<h4>$1</h4>')
      .replace(/\*\*(.*?)\*\*/gim, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/gim, '<em>$1</em>')
      .replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>')
      .replace(/---/gim, '<hr style="border:none; border-top:1px solid rgba(212,175,55,0.2); margin:12px 0;">')
      .replace(/\n\n/gim, '</p><p>')
      .replace(/\n/gim, '<br>');

    html = `<p>${html}</p>`;

    // 将主要人名转化为可点击图谱标签
    const coreNames = ["范闲", "叶轻眉", "庆帝", "五竹", "陈萍萍", "范建", "林婉儿", "范若若", "费介", "长公主", "海棠朵朵", "王启年", "苦荷", "四顾剑"];
    coreNames.forEach(name => {
      // 避免重复嵌套在 <strong> 等标签中时替换损坏
      const reg = new RegExp(`(?<!data-char=")${name}(?!">)`, "g");
      html = html.replace(reg, `<span class="char-link" data-char="${name}">${name}</span>`);
    });

    return html;
  }

  escapeHtml(str) {
    return (str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}
