export type SiteConfig = {
  site_name: string;
  wordmark_lines: string[];
  home_title_left_lines: string[];
  home_title_right_lines: string[];
  intro_lines: string[];
  about_label: string;
  about_title: string;
  about_body: string;
  about_why_title: string;
  about_why_body: string;
  about_feature_search_title: string;
  about_feature_search_body: string;
  about_feature_read_title: string;
  about_feature_read_body: string;
  about_feature_knowledge_title: string;
  about_feature_knowledge_body: string;
  about_ingestion_title: string;
  about_ingestion_body: string;
  about_access_title: string;
  about_access_body: string;
  about_rights_title: string;
  about_rights_body: string;
  about_privacy_title: string;
  about_privacy_body: string;
  about_warning_title: string;
  about_warning_body: string;
  copyright_text: string;
  navigation: {
    home: string;
    explore: string;
    theory_schools: string;
    scholars: string;
    topics: string;
    search: string;
  };
  sections: {
    featured: string;
    recent: string;
    random: string;
    featured_topic: string;
    theory_schools: string;
    search: string;
    scholars: string;
  };
};

export const defaultSiteConfig: SiteConfig = {
  site_name: "社会理论书库",
  wordmark_lines: ["SOCIAL", "THEORY", "LIBRARY"],
  home_title_left_lines: ["社会理论", "如何被感知"],
  home_title_right_lines: ["阅读就是", "方法"],
  intro_lines: [
    "一座面向社会科学研究与学习的开放书库。",
    "检索原文，回到具体页码，在完整语境中阅读与引用。",
  ],
  about_label: "关于书库",
  about_title: "从原文出发",
  about_body: "本书库面向社会科学研究与学习，提供公开阅读、全文检索、页码定位和规范引用。",
  about_why_title: "为什么建设这座书库",
  about_why_body: "在研究与教学中，许多概念与引文被反复引用，却常常脱离了原先的语境。关键词检索简化了查找，也可能让段落与思想之间的关系变得模糊。我希望通过系统化的数字化与组织，将关键词、思想与引文重新连接回它们最初所在的页面与文本之中，让阅读者能够看到完整的论述与原始语境。",
  about_feature_search_title: "寻找原始出处",
  about_feature_search_body: "按书名、作者、概念或你记得的句子进行检索，快速定位到原始文本中的确切页面。",
  about_feature_read_title: "阅读与整理",
  about_feature_read_body: "在线阅读，记录进度，添加书签、划线与高亮，并撰写个人笔记。",
  about_feature_knowledge_title: "理解知识关系",
  about_feature_knowledge_body: "按学者、流派与专题浏览，发现文本之间的关联，理解思想的发展。",
  about_ingestion_title: "资料如何进入书库",
  about_ingestion_body: "上传的文件会经历文本提取或 OCR、元数据识别、文本清理与结构化处理，并通过关系建议后，由人工进行内容核对与校订，确认无误后发布到书库供检索与阅读。",
  about_access_title: "开放原则与使用边界",
  about_access_body: "提供检索与公共阅读服务，致力于降低知识获取门槛，支持学习、研究与教学等合理使用。",
  about_rights_title: "版权与资源来源",
  about_rights_body: "书库收录的所有内容版权归原始权利人所有。我们遵循合理使用原则，仅提供检索与在线阅读。",
  about_privacy_title: "隐私",
  about_privacy_body: "你的个人笔记、标注与阅读记录默认仅对你可见，不会公开或分享给任何第三方。",
  about_warning_title: "请把系统结果视为阅读入口",
  about_warning_body: "OCR 识别、观点检索与自动分类可能存在错误或遗漏，系统结果仅供参考。正式引用与学术写作仍请以原始页面为准。",
  copyright_text: "© 2026 社会理论书库",
  navigation: {
    home: "首页",
    explore: "探索",
    theory_schools: "理论流派",
    scholars: "学者",
    topics: "主题",
    search: "搜索",
  },
  sections: {
    featured: "精选馆藏",
    recent: "最近入库",
    random: "随机推荐",
    featured_topic: "精选主题",
    theory_schools: "理论流派",
    search: "搜索书库",
    scholars: "学者聚焦",
  },
};
