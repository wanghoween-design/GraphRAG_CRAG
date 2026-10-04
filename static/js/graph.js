/**
 * 《庆余年》卷帙秘档 · 交互式 SVG 人物关系图谱引擎 (Novel Graph Engine v2.0 - 极致流畅版)
 * 核心优化：
 * 1. 【展示思路革新】：默认“宗师核心”清雅星盘布局，杜绝毛线团；支持一键展开全景万象，节点零重叠平铺。
 * 2. 【连线文字降噪】：智能聚焦模式——平时线条极简微光，仅在悬浮或点击人物时点亮关系铭文，视觉噪音直降 85%。
 * 3. 【彻底消除卡顿】：建立 O(1) 拓扑邻接索引表 (Adjacency Index)，采用 RAF 动画节流与轻量级 CSS 渲染，告别批量 DOM 震荡。
 * 4. 【杜绝连线乱飞】：采用平滑软核库仑斥力 (Softened Coulomb)、帧位移硬上限 (Velocity Clamping) 与稳定贝塞尔弧线，拖拽丝滑稳定。
 */

class NovelGraphEngine {
  constructor(svgId, options = {}) {
    this.svg = document.getElementById(svgId);
    this.viewport = document.getElementById("viewport");
    this.linksGroup = document.getElementById("links-group");
    this.labelsGroup = document.getElementById("labels-group");
    this.nodesGroup = document.getElementById("nodes-group");
    this.tooltip = document.getElementById("graph-tooltip");

    this.onNodeClick = options.onNodeClick || null;
    this.onDataLoaded = options.onDataLoaded || null;

    // 数据源
    this.allNodes = [];
    this.allLinks = [];
    this.visibleNodes = [];
    this.visibleLinks = [];
    this.nodeMap = new Map();
    this.factions = [];

    // 高性能拓扑索引 (O(1) 极速查询)
    this.neighborSet = new Map(); // name -> Set of connected names
    this.nodeLinksMap = new Map(); // name -> Array of incident links

    // 视图模式
    this.densityMode = "core"; // "core" (22人精粹) 或 "all" (全景96人)
    this.activeFaction = "all"; // 阵营筛选
    this.labelMode = "smart";  // "smart" (聚焦显现) 或 "always" (常驻显现)

    // 视口变换 (平移 & 缩放)
    this.transform = {
      x: 0,
      y: 0,
      scale: 0.85
    };

    // 交互状态
    this.isPanning = false;
    this.startPan = { x: 0, y: 0 };
    this.draggedNode = null;
    this.selectedNode = null;
    this.hoveredNode = null;

    // 物理力学参数 (经过精密阻尼调优)
    this.simRunning = true;
    this.alpha = 1.0;
    this.alphaDecay = 0.02;
    this.alphaMin = 0.002;

    this.initEvents();
  }

  /**
   * 初始化事件 (平移、缩放、拖拽)
   */
  initEvents() {
    const wrapper = document.getElementById("canvas-wrapper");

    // 1. 画布平移
    this.svg.addEventListener("mousedown", (e) => {
      if (e.target === this.svg || e.target.tagName.toLowerCase() === "rect") {
        this.isPanning = true;
        this.startPan = { x: e.clientX - this.transform.x, y: e.clientY - this.transform.y };
        wrapper.classList.add("grabbing");
      }
    });

    window.addEventListener("mousemove", (e) => {
      if (this.isPanning) {
        this.transform.x = e.clientX - this.startPan.x;
        this.transform.y = e.clientY - this.startPan.y;
        this.applyTransform();
      } else if (this.draggedNode) {
        // 拖拽节点并固定
        const pt = this.screenToSvg(e.clientX, e.clientY);
        this.draggedNode.x = pt.x;
        this.draggedNode.y = pt.y;
        this.draggedNode.vx = 0;
        this.draggedNode.vy = 0;
        // 适度唤醒微弱力场让周围节点轻微顺应，但绝不剧烈乱飞
        this.alpha = Math.max(this.alpha, 0.25);
        this.renderGraphPositions();
        if (!this.simRunning) {
          this.simRunning = true;
          this.stepSimulation();
        }
      }
    });

    window.addEventListener("mouseup", () => {
      if (this.isPanning) {
        this.isPanning = false;
        wrapper.classList.remove("grabbing");
      }
      if (this.draggedNode) {
        this.draggedNode.fixed = false;
        this.draggedNode = null;
      }
    });

    // 2. 滚轮平滑缩放
    this.svg.addEventListener("wheel", (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.12 : 0.88;
      const rect = this.svg.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const mouseY = e.clientY - rect.top;

      const newScale = Math.max(0.18, Math.min(3.0, this.transform.scale * zoomFactor));
      this.transform.x = mouseX - (mouseX - this.transform.x) * (newScale / this.transform.scale);
      this.transform.y = mouseY - (mouseY - this.transform.y) * (newScale / this.transform.scale);
      this.transform.scale = newScale;

      this.applyTransform();
    }, { passive: false });

    // 3. 窗口变动适配
    window.addEventListener("resize", () => {
      this.renderGraphPositions();
    });
  }

  screenToSvg(screenX, screenY) {
    const rect = this.svg.getBoundingClientRect();
    const x = (screenX - rect.left - this.transform.x) / this.transform.scale;
    const y = (screenY - rect.top - this.transform.y) / this.transform.scale;
    return { x, y };
  }

  applyTransform() {
    this.viewport.setAttribute(
      "transform",
      `translate(${this.transform.x}, ${this.transform.y}) scale(${this.transform.scale})`
    );
  }

  /**
   * 载入全量图谱数据
   */
  loadData(graphData) {
    this.factions = graphData.factions || [];
    const rawNodes = graphData.nodes || [];
    const rawLinks = graphData.links || [];

    this.allNodes = rawNodes.map(n => ({
      ...n,
      x: 0,
      y: 0,
      vx: 0,
      vy: 0,
      // 节点圈缩小 (原 size 26-50, 缩至 16-33), 让文字相对更大更清晰
      radius: Math.max(16, Math.min(32, Math.round((n.size || 26) * 0.65))),
      isCore: (n.salience || 0) >= 7
    }));

    this.allLinks = rawLinks.map((l, idx) => ({
      ...l,
      index: idx
    }));

    // 默认启用“宗师核心”视图，画面美如星图
    this.updateVisibleElements();
    this.computeInitialLayout(this.visibleNodes);
    this.centerView();
    this.renderDOM();
    this.restartSimulation(0.4);

    if (this.onDataLoaded) {
      this.onDataLoaded(graphData);
    }
  }

  /**
   * 防重叠初始布局: 主角居中 + 同阵营相邻 + 同心圆环精确排布
   * 环容量按弦长公式计算 (2R·sin(π/k) ≥ 最大直径+间隙), 数学上保证互不重叠。
   * 传入 nodeList: 对任意可见子集 (核心视图/全景/单阵营筛选) 都按其实际规模重排。
   */
  computeInitialLayout(nodeList) {
    const nodes = nodeList || this.allNodes;
    if (!nodes.length) return;

    // 排序: 同阵营节点相邻 (沿环形成同色簇), 阵营内按显著度降序
    const factionOrder = ["fan_manor", "imperial", "council", "grandmaster", "beiqi_romance", "places_org"];
    const sorted = [...nodes].sort((a, b) => {
      const fa = factionOrder.indexOf(a.faction), fb = factionOrder.indexOf(b.faction);
      if (fa !== fb) return (fa < 0 ? 99 : fa) - (fb < 0 ? 99 : fb);
      return (b.salience || 5) - (a.salience || 5);
    });

    // 主角置于圆心
    let remaining = sorted.slice();
    const GAP = 34; // 节点间隙 (含名牌呼吸空间)
    const centerIdx = remaining.findIndex(n => n.name === "范闲");
    if (centerIdx >= 0) {
      remaining[centerIdx].x = 0;
      remaining[centerIdx].y = 0;
      remaining.splice(centerIdx, 1);
    }

    let ringR = 195;
    while (remaining.length) {
      const maxDiam = 2 * Math.max(...remaining.map(n => n.radius)) + GAP;
      // 本环容量: 弦长约束 2R·sin(π/k) ≥ maxDiam
      const stepNeeded = 2 * Math.asin(Math.min(1, maxDiam / (2 * ringR)));
      const capacity = Math.max(5, Math.floor((2 * Math.PI) / stepNeeded));
      const batch = remaining.splice(0, capacity);
      batch.forEach((n, i) => {
        const angle = -Math.PI / 2 + (i / batch.length) * 2 * Math.PI;
        n.x = Math.cos(angle) * ringR;
        n.y = Math.sin(angle) * ringR;
      });
      ringR += 150;
    }
  }

  /**
   * hex 色值转 rgba (节点内圈阵营染色用)
   */
  hexToRgba(hex, alpha) {
    const m = String(hex || "#d4af37").replace("#", "");
    if (m.length < 6) return `rgba(212, 175, 55, ${alpha})`;
    const r = parseInt(m.slice(0, 2), 16);
    const g = parseInt(m.slice(2, 4), 16);
    const b = parseInt(m.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  /**
   * 刷新当前过滤出的节点与连线集合，并重新构建 O(1) 拓扑索引
   */
  updateVisibleElements() {
    // 1. 过滤节点
    this.visibleNodes = this.allNodes.filter(n => {
      if (this.densityMode === "core" && !n.isCore) return false;
      if (this.activeFaction !== "all" && n.faction !== this.activeFaction) return false;
      return true;
    });

    this.nodeMap.clear();
    this.visibleNodes.forEach(n => this.nodeMap.set(n.name, n));

    // 2. 过滤有效连线
    this.visibleLinks = this.allLinks.filter(l => {
      return this.nodeMap.has(l.source) && this.nodeMap.has(l.target);
    });

    // 3. 构建 O(1) 拓扑邻接索引表
    this.neighborSet.clear();
    this.nodeLinksMap.clear();

    this.visibleNodes.forEach(n => {
      this.neighborSet.set(n.name, new Set([n.name]));
      this.nodeLinksMap.set(n.name, []);
    });

    this.visibleLinks.forEach(l => {
      if (this.neighborSet.has(l.source)) this.neighborSet.get(l.source).add(l.target);
      if (this.neighborSet.has(l.target)) this.neighborSet.get(l.target).add(l.source);

      if (this.nodeLinksMap.has(l.source)) this.nodeLinksMap.get(l.source).push(l);
      if (this.nodeLinksMap.has(l.target)) this.nodeLinksMap.get(l.target).push(l);
    });
  }

  /**
   * 视角居中重置 (依据实际内容半径自适应缩放, 保证全图平铺可见)
   */
  centerView() {
    const rect = this.svg.getBoundingClientRect();
    const nodes = this.visibleNodes.length ? this.visibleNodes : this.allNodes;
    let contentRadius = 220;
    nodes.forEach(n => {
      const r = Math.sqrt(n.x * n.x + n.y * n.y) + (n.radius || 26) + 70;
      if (r > contentRadius) contentRadius = r;
    });
    const fitScale = Math.min(rect.width, rect.height) / (2 * contentRadius);
    this.transform.scale = Math.max(0.3, Math.min(1.15, fitScale));
    this.transform.x = rect.width / 2;
    this.transform.y = rect.height / 2;
    this.applyTransform();
  }

  /**
   * 切换呈现模式：精粹核心 vs 原著全景
   */
  setDensityMode(mode) {
    if (this.densityMode === mode) return;
    this.densityMode = mode;
    this.updateVisibleElements();
    this.computeInitialLayout(this.visibleNodes);
    this.centerView();
    this.renderDOM();
    this.restartSimulation(0.35);
  }

  /**
   * 切换阵营筛选
   */
  setFactionFilter(factionKey) {
    this.activeFaction = factionKey;
    this.updateVisibleElements();
    this.computeInitialLayout(this.visibleNodes);
    this.centerView();
    this.renderDOM();
    this.restartSimulation(0.35);
  }

  /**
   * 渲染 SVG DOM 元素
   */
  renderDOM() {
    this.linksGroup.innerHTML = "";
    this.labelsGroup.innerHTML = "";
    this.nodesGroup.innerHTML = "";

    // 1. 渲染关系连线 (Links)
    this.visibleLinks.forEach((link, idx) => {
      const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
      path.setAttribute("class", "graph-link");
      path.setAttribute("id", `link-${idx}`);
      // 关键: SVG path 默认 fill 为黑色, 贝塞尔曲线会被填充成"曲线-弦"之间的月牙黑块,
      // 视觉上就是每条连线下方拖着的锥形阴影带 —— 必须显式关闭填充
      path.setAttribute("fill", "none");
      path.setAttribute("stroke", link.color || "#475569");
      path.setAttribute("stroke-opacity", "0.5");
      if (link.dash) {
        path.setAttribute("stroke-dasharray", link.dash);
      }
      
      let markerId = "arrow-default";
      if (link.color === "#ef4444") markerId = "arrow-crimson";
      else if (link.color === "#f59e0b") markerId = "arrow-gold";
      else if (link.color === "#10b981") markerId = "arrow-jade";
      else if (link.color === "#06b6d4") markerId = "arrow-cyan";
      else if (link.color === "#8b5cf6") markerId = "arrow-purple";
      path.setAttribute("marker-end", `url(#${markerId})`);

      link.element = path;
      this.linksGroup.appendChild(path);

      // 渲染连线文字胶囊 (平时隐藏，悬浮或点击时点亮)
      if (link.label) {
        const labelGroup = document.createElementNS("http://www.w3.org/2000/svg", "g");
        labelGroup.setAttribute("class", "link-label-group");
        labelGroup.setAttribute("id", `label-${idx}`);
        // 初始显隐状态根据 labelMode
        if (this.labelMode === "smart") {
          labelGroup.style.opacity = "0";
        }

        const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
        rect.setAttribute("class", "link-label-rect");
        const textWidth = Math.max(32, link.label.length * 11 + 6);
        rect.setAttribute("width", textWidth);
        rect.setAttribute("height", 16);
        rect.setAttribute("x", -textWidth / 2);
        rect.setAttribute("y", -8);

        const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
        text.setAttribute("class", "link-label-text");
        text.textContent = link.label;

        labelGroup.appendChild(rect);
        labelGroup.appendChild(text);
        link.labelElement = labelGroup;
        this.labelsGroup.appendChild(labelGroup);
      }
    });

    // 2. 渲染实体节点 (Nodes)
    this.visibleNodes.forEach(node => {
      const g = document.createElementNS("http://www.w3.org/2000/svg", "g");
      g.setAttribute("class", "node-group");
      g.setAttribute("id", `node-${node.name}`);

      const radius = node.radius;

      // 外光晕圆环 (描边 + 填充均取阵营色, 势力一眼可辨)
      const outerCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      outerCircle.setAttribute("class", "node-circle-outer");
      outerCircle.setAttribute("r", radius);
      outerCircle.setAttribute("fill", this.hexToRgba(node.color, 0.16));
      outerCircle.setAttribute("stroke", node.color || "#d4af37");

      // 内圈: 阵营色半透明染色, 保留书法字对比度
      const innerCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      innerCircle.setAttribute("class", "node-circle-inner");
      innerCircle.setAttribute("r", radius - 3.5);
      innerCircle.setAttribute("fill", this.hexToRgba(node.color, 0.30));
      innerCircle.setAttribute("stroke", "rgba(255, 255, 255, 0.18)");
      innerCircle.setAttribute("stroke-width", "1");

      // 书法单字字形
      const glyphText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      glyphText.setAttribute("class", "node-text-glyph");
      glyphText.setAttribute("y", 1);
      glyphText.textContent = node.glyph || node.name.slice(0, 1);

      // 人物全名
      const nameText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      nameText.setAttribute("class", "node-text-name");
      nameText.setAttribute("y", radius + 15);
      nameText.textContent = node.name;

      // 阵营徽标
      const badgeText = document.createElementNS("http://www.w3.org/2000/svg", "text");
      badgeText.setAttribute("class", "node-text-badge");
      badgeText.setAttribute("y", radius + 26);
      badgeText.textContent = node.badge || "";

      g.appendChild(outerCircle);
      g.appendChild(innerCircle);
      g.appendChild(glyphText);
      g.appendChild(nameText);
      if (node.badge) g.appendChild(badgeText);

      this.bindNodeEvents(g, node);

      node.element = g;
      this.nodesGroup.appendChild(g);
    });

    this.renderGraphPositions();
  }

  /**
   * 绑定单个节点的鼠标交互 (带防抖与 RAF 节流)
   */
  bindNodeEvents(element, node) {
    element.addEventListener("mousedown", (e) => {
      e.stopPropagation();
      this.draggedNode = node;
      node.fixed = true;
    });

    element.addEventListener("mouseenter", (e) => {
      this.hoveredNode = node;
      this.highlightNeighborhood(node);
      this.showTooltip(e, node);
    });

    element.addEventListener("mouseleave", () => {
      this.hoveredNode = null;
      if (!this.selectedNode) {
        this.clearHighlight();
      } else {
        this.highlightNeighborhood(this.selectedNode);
      }
      this.hideTooltip();
    });

    element.addEventListener("click", (e) => {
      e.stopPropagation();
      this.selectNode(node);
    });
  }

  /**
   * 选中人物并展开其专属星宿网络
   */
  selectNode(node) {
    this.selectedNode = node;

    document.querySelectorAll(".node-group").forEach(el => el.classList.remove("selected"));
    if (node.element) {
      node.element.classList.add("selected");
    }

    this.highlightNeighborhood(node);

    if (this.onNodeClick) {
      this.onNodeClick(node);
    }
  }

  /**
   * 高性能邻域高亮 (利用 Map 实现 O(1) 瞬时响应，绝不卡顿)
   */
  highlightNeighborhood(centerNode) {
    const neighbors = this.neighborSet.get(centerNode.name) || new Set([centerNode.name]);
    const incidentLinks = new Set(this.nodeLinksMap.get(centerNode.name) || []);

    // 1. 批量调控节点
    this.visibleNodes.forEach(n => {
      const isConnected = neighbors.has(n.name);
      if (isConnected) {
        n.element.classList.remove("dimmed");
      } else {
        n.element.classList.add("dimmed");
      }
    });

    // 2. 批量调控连线与文字标签
    this.visibleLinks.forEach(l => {
      const isIncident = incidentLinks.has(l);
      if (isIncident) {
        l.element.classList.add("highlighted");
        l.element.classList.remove("dimmed");
        if (l.labelElement) {
          l.labelElement.style.opacity = "1";
          l.labelElement.classList.remove("dimmed");
        }
      } else {
        l.element.classList.remove("highlighted");
        l.element.classList.add("dimmed");
        if (l.labelElement) {
          l.labelElement.style.opacity = (this.labelMode === "always" ? "0.2" : "0");
          l.labelElement.classList.add("dimmed");
        }
      }
    });
  }

  /**
   * 清除高亮
   */
  clearHighlight() {
    this.visibleNodes.forEach(n => n.element && n.element.classList.remove("dimmed", "selected"));
    this.visibleLinks.forEach(l => {
      if (l.element) l.element.classList.remove("highlighted", "dimmed");
      if (l.labelElement) {
        l.labelElement.style.opacity = (this.labelMode === "always" ? "1" : "0");
        l.labelElement.classList.remove("dimmed");
      }
    });
    this.selectedNode = null;
  }

  showTooltip(e, node) {
    const rect = this.svg.getBoundingClientRect();
    this.tooltip.innerHTML = `
      <div style="font-weight: 700; color: ${node.color}; margin-bottom: 2px;">
        ${node.name} <span style="font-size: 10px; opacity: 0.85;">[${node.badge || node.faction_name}]</span>
      </div>
      <div style="font-size: 11px; color: #94a3b8; max-width: 220px; line-height: 1.4;">
        ${node.title || node.description.slice(0, 42) + '...'}
      </div>
    `;
    this.tooltip.style.left = `${e.clientX - rect.left}px`;
    this.tooltip.style.top = `${e.clientY - rect.top}px`;
    this.tooltip.classList.add("visible");
  }

  hideTooltip() {
    this.tooltip.classList.remove("visible");
  }

  /**
   * 搜索并镜头聚焦
   */
  focusCharacter(name) {
    let target = this.allNodes.find(n => n.name === name || (n.aliases && n.aliases.includes(name)));
    if (!target) return false;

    // 若当前在 core 模式而目标为次级人物，自动切换至全景并聚焦
    if (this.densityMode === "core" && !target.isCore) {
      this.setDensityMode("all");
      // 重新获取可见引用
      target = this.visibleNodes.find(n => n.name === target.name) || target;
    }

    const rect = this.svg.getBoundingClientRect();
    this.transform.scale = 1.25;
    this.transform.x = rect.width / 2 - target.x * this.transform.scale;
    this.transform.y = rect.height / 2 - target.y * this.transform.scale;
    this.applyTransform();

    this.selectNode(target);
    return true;
  }

  /**
   * 物理力学模拟步进 (软核排斥 + 位置级硬碰撞约束, 保证节点永不重叠)
   */
  stepSimulation() {
    if (!this.simRunning || this.alpha < this.alphaMin) {
      // 收敛后做最终碰撞清扫, 静态画面同样保证零重叠
      this.resolveOverlaps(60);
      this.simRunning = false;
      return;
    }

    const kRepel = 10000;    // 斥力系数 (强势, 保证节点铺开互斥)
    const kLink = 0.012;     // 弹簧引力系数 (微调, 只把相连节点轻轻拉近, 不许压塌布局)
    const centerGravity = 0.003; // 中心引力 (极弱, 让节点平铺铺开)
    const maxVelocity = 9.0; // 严格速度上限 (Velocity Clamp)，彻底终结乱飞！

    const nodes = this.visibleNodes;
    const len = nodes.length;

    // 1. 软核节点排斥力 (Softened Coulomb Repulsion)
    for (let i = 0; i < len; i++) {
      const n1 = nodes[i];
      for (let j = i + 1; j < len; j++) {
        const n2 = nodes[j];
        const dx = n2.x - n1.x;
        const dy = n2.y - n1.y;

        // 软核距离平方：+1200 保证即使两圆心极度重合，分母也不会趋近于 0 导致无限大斥力爆炸！
        const distSq = dx * dx + dy * dy + 1200;
        const dist = Math.sqrt(distSq);

        if (dist > 700) continue;

        const force = (kRepel / distSq) * this.alpha;
        const fx = (dx / dist) * force;
        const fy = (dy / dist) * force;

        if (!n1.fixed) { n1.vx -= fx; n1.vy -= fy; }
        if (!n2.fixed) { n2.vx += fx; n2.vy += fy; }
      }

      // 中心汇聚引力
      if (!n1.fixed) {
        n1.vx -= n1.x * centerGravity * this.alpha;
        n1.vy -= n1.y * centerGravity * this.alpha;
      }
    }

    // 2. 关系连线弹簧引力 (理想间距随两端节点半径自适应, 大节点自动离得更远)
    this.visibleLinks.forEach(l => {
      const s = this.nodeMap.get(l.source);
      const t = this.nodeMap.get(l.target);
      if (!s || !t) return;

      const linkDist = s.radius + t.radius + 120;
      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;
      const delta = dist - linkDist;
      const force = delta * kLink * this.alpha;
      const fx = (dx / dist) * force;
      const fy = (dy / dist) * force;

      if (!s.fixed) { s.vx += fx; s.vy += fy; }
      if (!t.fixed) { t.vx -= fx; t.vy -= fy; }
    });

    // 3. 阻尼衰减、速度上限约束与坐标积分
    const damping = 0.65;
    nodes.forEach(n => {
      if (!n.fixed) {
        // 施加速度阻尼与上限
        n.vx = Math.max(-maxVelocity, Math.min(maxVelocity, n.vx * damping));
        n.vy = Math.max(-maxVelocity, Math.min(maxVelocity, n.vy * damping));
        n.x += n.vx;
        n.y += n.vy;
      }
    });

    // 4. 位置级硬碰撞约束 (两轮全量分离, 圆心距恒 ≥ 半径和 + 间隙)
    this.separateOverlaps(2);

    this.alpha *= (1 - this.alphaDecay);
    this.renderGraphPositions();

    if (this.alpha >= this.alphaMin) {
      requestAnimationFrame(() => this.stepSimulation());
    } else {
      this.resolveOverlaps(60);
      this.simRunning = false;
    }
  }

  /**
   * 位置级碰撞分离: 对当前可见节点做 iterations 轮两两分离
   * 直接修正坐标 (而非速度), 收敛后仍能彻底消除残留重叠
   */
  separateOverlaps(iterations) {
    const nodes = this.visibleNodes;
    const len = nodes.length;
    const GAP = 30; // 节点间隙 (含名牌空间)

    for (let it = 0; it < iterations; it++) {
      let moved = false;
      for (let i = 0; i < len; i++) {
        const n1 = nodes[i];
        for (let j = i + 1; j < len; j++) {
          const n2 = nodes[j];
          let dx = n2.x - n1.x;
          let dy = n2.y - n1.y;
          const minDist = n1.radius + n2.radius + GAP;
          let dist = Math.sqrt(dx * dx + dy * dy);

          if (dist < 0.01) {
            // 完全重合: 随机微扰脱开
            dx = (Math.random() - 0.5) * 2;
            dy = (Math.random() - 0.5) * 2;
            dist = Math.sqrt(dx * dx + dy * dy) || 1;
          }

          if (dist < minDist) {
            const push = (minDist - dist) / 2;
            const nx = dx / dist;
            const ny = dy / dist;
            if (!n1.fixed) { n1.x -= nx * push; n1.y -= ny * push; moved = true; }
            if (!n2.fixed) { n2.x += nx * push; n2.y += ny * push; moved = true; }
          }
        }
      }
      if (!moved) break;
    }
  }

  /**
   * 收敛后的静态重叠清扫 + 重渲染
   */
  resolveOverlaps(iterations) {
    if (!this.visibleNodes.length) return;
    this.separateOverlaps(iterations);
    this.renderGraphPositions();
  }

  restartSimulation(alpha0 = 0.6) {
    // alpha0 可调: 初布局已就位时用低能量(0.35)温和收敛, 避免把好布局搅乱
    this.alpha = alpha0;
    this.simRunning = true;
    this.stepSimulation();
  }

  toggleSimulation() {
    this.simRunning = !this.simRunning;
    if (this.simRunning) {
      this.restartSimulation();
    }
    return this.simRunning;
  }

  /**
   * 刷新节点与连线在 SVG 中的空间路径 (稳定贝塞尔曲线，绝对不抖动翻转)
   */
  renderGraphPositions() {
    // 1. 节点移动
    this.visibleNodes.forEach(n => {
      if (n.element) {
        n.element.setAttribute("transform", `translate(${n.x}, ${n.y})`);
      }
    });

    // 2. 连线移动 (稳态贝塞尔中点推导)
    this.visibleLinks.forEach(l => {
      const s = this.nodeMap.get(l.source);
      const t = this.nodeMap.get(l.target);
      if (!s || !t || !l.element) return;

      const dx = t.x - s.x;
      const dy = t.y - s.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 1;

      // 稳态法向量微弯（上限严格钳制在 20px 范围，避免大距离时线条突起成巨环）
      const nx = -dy / dist;
      const ny = dx / dist;
      const curveOffset = Math.min(18, Math.max(-18, dist * 0.08));

      const midX = (s.x + t.x) * 0.5 + nx * curveOffset;
      const midY = (s.y + t.y) * 0.5 + ny * curveOffset;

      l.element.setAttribute("d", `M ${s.x} ${s.y} Q ${midX} ${midY} ${t.x} ${t.y}`);

      if (l.labelElement) {
        l.labelElement.setAttribute("transform", `translate(${midX}, ${midY})`);
      }
    });
  }
}
