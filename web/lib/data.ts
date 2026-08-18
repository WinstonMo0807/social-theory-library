export type Work = {
  id: string;
  workId?: string;
  editionId?: string;
  slug: string;
  title: string;
  originalTitle?: string;
  author: string;
  year: string;
  kind: "图书" | "期刊论文" | "学位论文" | "研究报告";
  school: string;
  summary: string;
  cover: "dark" | "paper" | "cream" | "line";
  coverImage?: string;
  pages: number;
  language?: string;
  authors?: { name: string; slug?: string | null }[];
  theories?: { name: string; slug: string }[];
  topics?: { name: string; slug: string }[];
  theoryAssociations?: {
    id: string;
    node: { id: string; name: string; foreign_name: string; slug: string; type: string };
    role: string;
    role_label: string;
    strength: string;
    evidence: {
      id: string;
      page_number: number;
      page_end: number | null;
      printed_page_label: string;
      quote: string;
      reader_href: string;
    }[];
  }[];
  outline?: { index: number; printed_label: string; chapter_title: string }[];
};

export type Scholar = {
  id?: string;
  slug: string;
  name: string;
  originalName: string;
  portrait?: string;
  years: string;
  school: string;
  concerns: string[];
  biography: string;
};

export type TheorySchool = {
  slug: string;
  name: string;
  description: string;
  books: number;
  scholars: number;
  symbol: string;
};

export const works: Work[] = [
  {
    id: "asset-discipline",
    slug: "discipline-and-punish",
    title: "规训与惩罚",
    originalTitle: "Discipline and Punish",
    author: "米歇尔·福柯",
    year: "1975",
    kind: "图书",
    school: "后结构主义",
    summary: "讨论现代制度如何借助观察、训练与规范塑造身体和主体。",
    cover: "dark",
    pages: 548,
  },
  {
    id: "asset-state-revolution",
    slug: "state-and-revolution",
    title: "国家与革命",
    author: "弗拉基米尔·列宁",
    year: "1917",
    kind: "图书",
    school: "马克思主义",
    summary: "围绕国家、阶级统治与革命转型展开的经典论述。",
    cover: "paper",
    pages: 232,
  },
  {
    id: "asset-presentation-self",
    slug: "presentation-of-self",
    title: "日常生活中的自我呈现",
    author: "欧文·戈夫曼",
    year: "1959",
    kind: "图书",
    school: "符号互动论",
    summary: "以戏剧分析理解面对面互动中的印象管理与情境秩序。",
    cover: "cream",
    pages: 304,
  },
  {
    id: "asset-orientalism",
    slug: "orientalism",
    title: "东方学",
    author: "爱德华·萨义德",
    year: "1978",
    kind: "图书",
    school: "后殖民理论",
    summary: "分析西方如何在知识生产中建构东方，并维持权力关系。",
    cover: "paper",
    pages: 432,
  },
  {
    id: "asset-protestant-ethic",
    slug: "protestant-ethic",
    title: "新教伦理与资本主义精神",
    author: "马克斯·韦伯",
    year: "1905",
    kind: "图书",
    school: "理解社会学",
    summary: "追问宗教伦理与现代资本主义行动方式之间的历史关系。",
    cover: "line",
    pages: 286,
  },
  {
    id: "asset-distinction",
    slug: "distinction",
    title: "区分",
    author: "皮埃尔·布迪厄",
    year: "1979",
    kind: "图书",
    school: "布迪厄社会学",
    summary: "从品味与生活方式入手，揭示文化判断中的阶级结构。",
    cover: "cream",
    pages: 648,
  },
  {
    id: "asset-gender-trouble",
    slug: "gender-trouble",
    title: "性别麻烦",
    author: "朱迪斯·巴特勒",
    year: "1990",
    kind: "图书",
    school: "女性主义",
    summary: "质疑稳定性别身份的假定，并提出性别表演性的分析。",
    cover: "dark",
    pages: 272,
  },
  {
    id: "asset-surveillance-capitalism",
    slug: "surveillance-capitalism",
    title: "监控资本主义时代",
    author: "肖莎娜·祖博夫",
    year: "2019",
    kind: "图书",
    school: "科技与社会研究",
    summary: "分析平台如何提取行为数据并形成新的经济与权力结构。",
    cover: "dark",
    pages: 704,
  },
];

export const scholars: Scholar[] = [
  {
    slug: "michel-foucault",
    name: "米歇尔·福柯",
    originalName: "Michel Foucault",
    years: "1926—1984",
    school: "后结构主义",
    concerns: ["权力", "知识", "规训", "主体性"],
    biography: "法国哲学家和思想史研究者。他通过档案研究考察知识制度、权力技术与现代主体的形成。",
  },
  {
    slug: "pierre-bourdieu",
    name: "皮埃尔·布迪厄",
    originalName: "Pierre Bourdieu",
    years: "1930—2002",
    school: "布迪厄社会学",
    concerns: ["惯习", "场域", "资本", "不平等"],
    biography: "法国社会学家。他发展了关系性的实践理论，用惯习、场域与资本分析文化、教育和权力。",
  },
  {
    slug: "judith-butler",
    name: "朱迪斯·巴特勒",
    originalName: "Judith Butler",
    years: "1956—",
    school: "女性主义",
    concerns: ["性别", "表演性", "主体", "承认"],
    biography: "美国哲学家与性别理论研究者，其工作重新讨论性别身份、规范与政治行动。",
  },
  {
    slug: "karl-marx",
    name: "卡尔·马克思",
    originalName: "Karl Marx",
    years: "1818—1883",
    school: "马克思主义",
    concerns: ["阶级", "资本", "劳动", "历史"],
    biography: "德国思想家，以政治经济学批判解释资本积累、劳动关系与社会历史变化。",
  },
  {
    slug: "frantz-fanon",
    name: "弗朗茨·法农",
    originalName: "Frantz Fanon",
    years: "1925—1961",
    school: "后殖民理论",
    concerns: ["殖民", "种族", "暴力", "解放"],
    biography: "精神科医生与反殖民思想家，关注殖民经验对主体和政治解放的影响。",
  },
  {
    slug: "bell-hooks",
    name: "贝尔·胡克斯",
    originalName: "bell hooks",
    years: "1952—2021",
    school: "女性主义",
    concerns: ["种族", "性别", "教育", "文化"],
    biography: "美国女性主义理论家和文化批评家，关注种族、阶级与性别交叉处的支配和解放。",
  },
];

export const theorySchools: TheorySchool[] = [
  { slug: "marxism", name: "马克思主义", description: "阶级、资本与历史变化", books: 126, scholars: 78, symbol: "M" },
  { slug: "structural-functionalism", name: "结构功能主义", description: "相互依存的制度与社会秩序", books: 92, scholars: 56, symbol: "SF" },
  { slug: "symbolic-interactionism", name: "符号互动论", description: "日常互动中的意义生成", books: 78, scholars: 54, symbol: "SI" },
  { slug: "postcolonial-theory", name: "后殖民理论", description: "权力、表述与殖民历史", books: 101, scholars: 63, symbol: "PC" },
  { slug: "feminism", name: "女性主义", description: "性别秩序、父权制与社会变化", books: 112, scholars: 92, symbol: "F" },
  { slug: "critical-theory", name: "批判理论", description: "意识形态、解放与社会批判", books: 89, scholars: 61, symbol: "CT" },
  { slug: "rational-choice", name: "理性选择理论", description: "行动、策略与制度约束", books: 64, scholars: 38, symbol: "RC" },
  { slug: "bourdieu", name: "布迪厄社会学", description: "惯习、场域与多种资本", books: 96, scholars: 67, symbol: "B" },
];

export const topic: {
  slug: string;
  name: string;
  description: string;
  concepts: string[];
  timeline: [string, string, string][];
} = {
  slug: "surveillance-and-society",
  name: "监控与社会",
  description:
    "从全景敞视到数字平台，本主题考察观察、记录与管理行为的技术和制度，并讨论监控如何塑造知识、治理、主体性与抵抗。",
  concepts: ["监控", "全景敞视", "凝视", "数据化", "生命政治", "控制", "隐私", "抵抗"],
  timeline: [
    ["1791", "全景敞视", "边沁提出以可见性组织秩序的建筑模型。"],
    ["1975", "规训权力", "福柯分析制度如何生产驯顺的身体。"],
    ["1990年代", "控制社会", "德勒兹讨论连续调节与流动控制。"],
    ["2000年代", "数据化", "数字系统持续捕捉和分类日常行为。"],
    ["2010年代至今", "监控资本主义", "行为数据成为预测和干预的经济资源。"],
  ],
};

export const stats = [
  ["28,450", "图书与论文"],
  ["1,240", "学者"],
  ["56+", "理论流派"],
];

export const siteConfig = {
  name: "社会理论书库",
  englishName: ["SOCIAL", "THEORY", "LIBRARY"],
  email: "contribute@example.org",
};
