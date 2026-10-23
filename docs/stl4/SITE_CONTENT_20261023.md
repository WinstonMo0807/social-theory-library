# M29 首页编排、关于与公共说明接续

2026-10-23，接续e5cbc3b。状态为预读与定位，未计新增实现。

已从唯一 final-r2 PDF 直接读取167–169页嵌入图，保存于tmp/pdfs/stl4-final-m29-20261023。终稿要求首页内容/关于我们/使用说明/帮助公告，主推模块排序、学者与主题选择，右侧内容设置/页面预览/更新记录，以及来源撤回、封面缺失、空槽位和移动编辑状态。原对象应引用，不复制成新馆藏；首页位置的显示开关不改变来源的发布状态。

已读取web/app/admin/about/page.tsx、web/components/admin/site-content-editor.tsx，定位api/catalog/editorial_issue_views.py的AdminSiteContentView/AdminSitePublishView/AdminSitePreviewView及services/editorial_issues.py的site_public_payload/site_target/site_payload/save_site/publish_site。后端相关函数正文尚未在本阶段逐项追踪，下一步从这些函数继续，不将定位当作审计完成。

当前SiteContentEditor仍是首页馆头/品牌/关于模块/页脚字段编辑与FixedPageEditor预览；原草稿/版本冲突/发布能力已有，但M29源对象编排主栏未按图接入，读取/保存和全页预览还需账户隔离及原请求查回核对。需要继续追踪原content placements、推荐服务及HomePublicView的最终公共投影，优先复用同一编排/修订服务，不再建第二套首页内容库。

下一步：追踪已有数据与调用链，核对公共首页最终图布局约束，实施源对象选择/顺序/标题导语/封面/显示设置，接真实预览与更新记录；同时补会话/版本/发布权限。保持旧关于与公共说明能力。尚未修改M29源码，未运行测试、浏览器或业务操作。

M28结束时296契约、96源码/72部分/41待实施；本次预读不改变统计。distribution0003、catalog0075/0076/0077、reading0022/23/24继续未执行。
