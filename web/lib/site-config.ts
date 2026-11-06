import type { WelcomeConfig, WelcomeBook } from "./welcome";
export type SiteConfig = {
  welcome?: WelcomeConfig;
  welcome_books?: WelcomeBook[];
  site_name: string;
  home_hero_image?: string;
  home_hero_alt?: string;
  home_hero_rendition_id?: string | null;
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
  home_title_left_lines: ["连接思想，"],
  home_title_right_lines: ["打开更大的世界"],
  intro_lines: [
    "汇聚社会理论的经典与当代，",
    "促进知识、研究与公众的对话。",
  ],
  about_label: "关于书库",
  about_title: "关于社会理论书库",
  about_body: "连接思想、开放知识，服务研究与公众。",
  about_why_title: "为什么建设这座书库",
  about_why_body: "在研究与教学中，许多概念与引文被反复引用，却常常脱离了原先的语境。关键词检索简化了查找，也可能让段落与思想之间的关系变得模糊。我希望通过系统化的数字化与组织，将关键词、思想与引文重新连接回它们最初所在的页面与文本之中，让阅读者能够看到完整的论述与原始语境。",
  about_feature_search_title: "我们收录什么",
  about_feature_search_body: "我们收录社会理论领域的重要图书与学术论文，包括经典著作、重要研究成果以及相关文献资料，涵盖不同理论流派、学者与主题。书目提供书名、作者、出版信息与简要介绍，并尽可能链接到可获取的原始文献，以便读者阅读、下载、复制和引用。",
  about_feature_read_title: "如何阅读与引用",
  about_feature_read_body: "每条书目尽可能提供指向原始文献（PDF 等）的链接，让读者回到作者的原文。我们同时提供标准的书目信息，方便在学术写作中引用。为保持学术的清晰性，我们将来源文本与编者的介绍、评述或导读加以区分，帮助读者在阅读原文的基础上形成自己的理解。",
  about_feature_knowledge_title: "内容与来源",
  about_feature_knowledge_body: "书目主要来自公开出版的学术资源，来源包括学术出版社、开放获取平台与可信的学术数据库。我们尽量提供稳定、可访问的原始文献链接，并在书目中标明来源信息。编者撰写的介绍、评述与导读仅用于提供背景与阅读参考，不替代或改变原作者的文本。",
  about_ingestion_title: "资料如何进入书库",
  about_ingestion_body: "上传的文件会经历文本提取或 OCR、元数据识别、文本清理与结构化处理，并通过关系建议后，由人工进行内容核对与校订，确认无误后发布到书库供检索与阅读。",
  about_access_title: "开放原则与使用边界",
  about_access_body: "提供检索与公共阅读服务，致力于降低知识获取门槛，支持学习、研究与教学等合理使用。",
  about_rights_title: "版权与资源来源",
  about_rights_body: "作品版权归原始权利人所有。原文访问与下载以所选来源显示的权限为准。若发现来源或授权问题，请通过反馈提供可核对的信息。",
  about_privacy_title: "隐私",
  about_privacy_body: "个人笔记、标注与阅读记录默认按账户隔离。分享或授权使用需要本人明确选择，可在读者中心查看和管理。",
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
