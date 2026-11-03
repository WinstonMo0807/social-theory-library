/** Small, explicitly bounded public-source corpus. Never imported into the library catalogue. */
export type Policy = {
  id: string; title: string; issuer: string; number: string; date: string;
  level: "国家级" | "省级" | "市级"; region: string; province?: string;
  kind: string; topic: string; source: string; sourceLabel: string;
  effective?: string; expires?: string; note: string;
  passages: { id: string; locator: string; text: string; lens: string }[];
};
export const corpusVersion = "public-sample-20261103-v1";
export const policies: Policy[] = [
  {
    id: "mohrss-2021-56", title: "关于维护新就业形态劳动者劳动保障权益的指导意见",
    issuer: "人力资源社会保障部等八部门", number: "人社部发〔2021〕56号", date: "2021-07-16",
    level: "国家级", region: "全国", kind: "行政规范性文件", topic: "劳动与社会保障",
    source: "https://www.mem.gov.cn/gk/zfxxgkpt/fdzdgknr/202201/t20220119_406920.shtml", sourceLabel: "应急管理部",
    note: "收录所列条款节选。分类为样本整理；本 Demo 未建立完整的修改、废止追踪。",
    passages: [
      { id: "mohrss-2", locator: "第一部分第（二）项", lens: "劳动关系与制度边界", text: "符合确立劳动关系情形的，企业应当依法与劳动者订立劳动合同。不完全符合确立劳动关系情形但企业对劳动者进行劳动管理（以下简称不完全符合确立劳动关系情形）的，指导企业与劳动者订立书面协议，合理确定企业与劳动者的权利义务。个人依托平台自主开展经营活动、从事自由职业等，按照民事法律调整双方的权利义务。" },
      { id: "mohrss-17", locator: "第四部分第（十七）项", lens: "集体协商与劳动者组织", text: "各级工会组织要加强组织和工作有效覆盖，拓宽维权和服务范围，积极吸纳新就业形态劳动者加入工会。加强对劳动者的思想政治引领，引导劳动者理性合法维权。监督企业履行用工责任，维护好劳动者权益。积极与行业协会、头部企业或企业代表组织开展协商，签订行业集体合同或协议，推动制定行业劳动标准。" },
    ],
  },
  {
    id: "shanghai-2022-1", title: "上海市关于维护新就业形态劳动者劳动保障权益的实施意见",
    issuer: "上海市人力资源和社会保障局等八部门", number: "沪人社规〔2022〕1号", date: "2022-01-04",
    level: "省级", region: "上海", kind: "行政规范性文件", topic: "劳动与社会保障",
    source: "https://service.shanghai.gov.cn/XingZhengWenDangKuJyh/XZGFDetails.aspx?docid=REPORT_NDOC_008160", sourceLabel: "上海市行政规范性文件数据库",
    effective: "2022-01-04", expires: "2026-12-31", note: "题名在界面中作简称。生效与有效期来自文件末段；是否另有调整仍须核对官方现行文本。",
    passages: [
      { id: "shanghai-10", locator: "第二部分第（十）项", lens: "算法控制与劳动者参与", text: "督促企业制定修订平台进入退出、订单分配、计件单价、抽成比例、报酬构成及支付、工作时间、奖惩等直接涉及劳动者权益的制度规则和平台算法，督促平台优化算法原则，不得将最严算法作为考核要求，遏制“以罚代管”，建立协商机制，充分听取工会或劳动者代表的意见建议，将结果公示并告知劳动者，保障劳动者对涉及切身利益重要事项的知情权。" },
      { id: "shanghai-5", locator: "第二部分第（五）项", lens: "收入分配与最低保障", text: "支持工会与行业协会、头部企业开展协商，订立行业集体合同或协议，合理确定行业劳动定额标准和计件单价。劳动者在提供正常劳动情况下，折算到小时后的劳动报酬应不低于本市最低工资标准。督促企业按时足额支付劳动报酬，不得克扣或者无故拖欠。引导企业建立劳动报酬合理增长机制，逐步提高劳动报酬水平。" },
      { id: "shanghai-14", locator: "第三部分第（十四）项", lens: "公共服务与城市融入", text: "加快城市综合服务网点建设，营造良好从业环境。推动在商业楼宇、居民小区等新就业形态劳动者集中居住区、商业区设置临时留驻点，提供必要的休息、停车、充电、饮水、如厕等条件，为新就业形态劳动者提供工作生活便利。鼓励企业积极采取措施，对劳动者住宿、子女教育、特殊困难方面给予关心帮助。" },
    ],
  },
  {
    id: "shaoxing-2022-53", title: "绍兴市维护新就业形态劳动者劳动保障权益实施办法",
    issuer: "绍兴市人力资源和社会保障局等九部门", number: "绍市人社发〔2022〕53号", date: "2022-10-24",
    level: "市级", region: "绍兴", province: "浙江", kind: "行政规范性文件", topic: "劳动与社会保障",
    source: "https://zjjcmspublic.oss-cn-hangzhou-zwynet-d01-a.internet.cloud.zj.gov.cn/jcms_files/jcms1/web2247/site/attach/0/ce272acd8e9e4ca68269fbc803ac1f6d.pdf", sourceLabel: "绍兴市人民政府公报 2022年第10期",
    note: "公报印刷页112；这里只收录该页两处节选，原文件与后续效力请查看官方公报。",
    passages: [
      { id: "shaoxing-1", locator: "第一部分「适用范围」· 公报第112页", lens: "政策对象与地方适用", text: "本市行政区域内新业态劳动者的劳动保障权益维护，适用本办法。本办法所称的新业态劳动者，是指依托互联网平台就业的网约配送员、网约客运（货运）汽车驾驶员、互联网营销师、快递员等人员。个人依托互联网平台自主开展经营活动、从事自由职业等，按照民事法律调整双方的权利义务。" },
      { id: "shaoxing-2", locator: "第二部分第（四）项 · 公报第112页", lens: "部门协同与监管责任", text: "市市场监督管理局：负责新业态网络交易监督管理；督促外卖平台企业落实主体责任，规范平台企业交易规则，落实平台企业对外卖配送员的食品安全培训和管理。" },
    ],
  },
  {
    id: "algorithm-2021-9", title: "互联网信息服务算法推荐管理规定",
    issuer: "国家互联网信息办公室等四部门", number: "国家互联网信息办公室等四部门令第9号", date: "2021-12-31",
    effective: "2022-03-01", level: "国家级", region: "全国", kind: "部门规章", topic: "算法与数字治理",
    source: "https://www.cac.gov.cn/2022-01/04/c_1642894606364259.htm", sourceLabel: "国家互联网信息办公室",
    note: "成文日期为2021年12月31日，官网页面发布日期为2022年1月4日；两者分别保存。现行效力待完整追踪。",
    passages: [
      { id: "algorithm-20", locator: "第二十条", lens: "算法调度与劳动保护", text: "算法推荐服务提供者向劳动者提供工作调度服务的，应当保护劳动者取得劳动报酬、休息休假等合法权益，建立完善平台订单分配、报酬构成及支付、工作时间、奖惩等相关算法。" },
      { id: "algorithm-17", locator: "第十七条第一款", lens: "技术选择与用户自主", text: "算法推荐服务提供者应当向用户提供不针对其个人特征的选项，或者向用户提供便捷的关闭算法推荐服务的选项。用户选择关闭算法推荐服务的，算法推荐服务提供者应当立即停止提供相关服务。" },
    ],
  },
  {
    id: "pipl-2021", title: "中华人民共和国个人信息保护法",
    issuer: "全国人民代表大会常务委员会", number: "中华人民共和国主席令第九十一号", date: "2021-08-20",
    effective: "2021-11-01", level: "国家级", region: "全国", kind: "法律", topic: "算法与数字治理",
    source: "https://www.cac.gov.cn/2021-08/20/c_1631050028355286.htm", sourceLabel: "国家互联网信息办公室转载中国人大网",
    note: "收录2021年公布文本的相关条款节选；本 Demo 不提供个案法律适用意见。",
    passages: [
      { id: "pipl-24", locator: "第二十四条第一款", lens: "自动化决策与公平", text: "个人信息处理者利用个人信息进行自动化决策，应当保证决策的透明度和结果公平、公正，不得对个人在交易价格等交易条件上实行不合理的差别待遇。" },
      { id: "pipl-27", locator: "第二十七条", lens: "公开信息与隐私边界", text: "个人信息处理者可以在合理的范围内处理个人自行公开或者其他已经合法公开的个人信息；个人明确拒绝的除外。个人信息处理者处理已公开的个人信息，对个人权益有重大影响的，应当依照本法规定取得个人同意。" },
    ],
  },
];
export const exampleQuestions = [
  "平台如何保障新就业形态劳动者的权益？",
  "上海和绍兴怎样规定平台企业的责任？",
  "算法治理如何回应劳动者与用户的自主权？",
];
export function policyCitation(policy: Policy, locator?: string) {
  return `${policy.issuer}：《${policy.title}》，${policy.number}，${policy.date}${locator ? `，${locator}` : ""}。官方来源：${policy.source}（访问日期：2026-11-03；样本节选）。`;
}
