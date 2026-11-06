# 首发账号与免费邮件

2026-11-06核验。用户已选择首发只用书库账号，Apple不接，Google后补。此决定替代此前将OAuth缺实现列为首发A项的记录。邮件仍只比较，未注册服务、提交域名、配置凭据或发信；生产没有变更。

## 免费方案的实际区别

| 服务 | 官方免费说明 | 对本书库的判断 |
|---|---|---|
| SendCloud大陆站 | FAQ写注册激活10封/日，可申请提升，上限200封/日；另有测试域名 | 可进一步核实的大陆候选。不能把申请上限当成默认额度或正式业务承诺；需确认个人主体、未在大陆提供服务的网站、自己的发信域名能否使用免费档。来源：[SendCloud FAQ](https://www.sendcloud.net/doc/faq/) |
| Aurora SendCloud | 另一站点文档写免费激活50封/日，额度随信誉变化 | 与上述大陆站不应混同。开户所在产品和实际控制台额度才是准数。来源：[Aurora额度说明](https://www.aurorasendcloud.com/docs/zh/QuickStart/Interpretation/) |
| 阿里云邮件推送 | 每个主账号共2000封，每天最多免费200封，超出收费 | 属于总量赠送，不是长期每天免费。来源：[官方FAQ](https://help.aliyun.com/zh/direct-mail/level) |
| 腾讯云邮件推送 | 共1000封，无到期日，用完转按日付费 | 也不是长期免费。官方另规定2026-03-02以后新个人实名账号不开放SMTP，需要API或符合条件的企业账户。来源：[价格](https://cloud.tencent.com/document/product/1288/47930)、[SMTP说明](https://cloud.tencent.com/document/product/1288/65749) |
| Brevo | 免费档每天300封，含事务邮件；官方写无时间期限、不需信用卡 | 若不强制大陆服务，这是当前免费规则最明确且现有代码直接支持的方案。域名和账户仍需验证，不能据免费额度保证实际送达。来源：[官方方案](https://help.brevo.com/hc/en-us/articles/208589409-About-Brevo-s-pricing-plans) |

建议：若长期免费优先，先选Brevo；若必须大陆服务，先向SendCloud核实免费档能否正式发送本站注册验证及找回密码邮件，再决定。没有开户和账户核验依据前，不承诺SendCloud一定适用，也不把一次性试用当永久免费。

## 已准备的SMTP接入

SMTP-CONFIG-01 D开发：原`api/config/settings.py`只选择Brevo/console，未读取SMTP连接参数；即使填环境变量，也无法供Django邮件传输使用。本轮增加原生SMTP后端选择及服务器、端口、账号、授权码、TLS/SSL、超时环境加载，未新增依赖或第二套邮件服务。`accounts.email_links`原有受理检查、队列、限流、单次有效链接、身份校验和错误处理保持。

`.env.example`只列占位设置。正式凭据只能进入服务器受限环境，不进聊天、浏览器构建、Git或公开接口。选定SMTP时配置`EMAIL_PROVIDER=smtp`；587通常使用STARTTLS，465通常使用隐式TLS，按服务商实际要求二选一，不能同时启用。默认未填主机时不能受理邮件。Brevo和显式`EMAIL_BACKEND`覆盖保持兼容。

4项定向检查实际执行Django原生邮件传输，使用模拟SMTP连接核对环境参数、STARTTLS/SSL、登录调用及发送调用，并检查未配置不可用、Brevo和显式后端保持；没有外部连接或邮件。命令：`../.venv/Scripts/python.exe -m pytest tests/test_smtp_environment_20261106.py --no-header -q`（api目录），退出0。pytest本地缓存目录警告不影响结果，未为此清理旧目录。真实SMTP认证、国际邮箱送达及恢复链接完成仍B。

选择服务后需要用户配合的只有：

1. 在服务商开立本人账户，确定免费档正式发信资格。
2. 在域名DNS添加该服务商给出的验证记录及邮件认证记录，不修改书库网站解析或NAS端口。
3. 将该服务的专用API密钥或SMTP授权码安全放入服务器受限配置，填写发件地址；不使用个人邮箱主密码。
4. 确认正式HTTPS站点地址，并授权向本人控制的收件箱发一轮验证/找回邮件，再检查真实结果。

当前`email_delivery_available=false`仍是准确的未配置状态。现有密码登录可用，不把“请求已受理”或模拟检查当实际收信通过。

## 账号页面的旧权限文案

AUTH-GUEST-COPY-01：实际打开内网登录页，页脚仍写公开检索/阅读/下载开放，访客入口又指向需要登录的`/explore`。`auth-page-frame.tsx`、`account-activation.tsx`及共用`auth-session-dialog.tsx`有相同旧说法，违反用户已确认的访客仅浏览网页规则，会让读者误以为可匿名阅读或进入反复登录的路径。

最小修复只更新上述文案：浏览公开页面，阅读PDF/下载/检索需登录。整页访客链接返回首页，弹窗保留关闭行为并改名“暂不登录”；不修改访问权限、转存逻辑或现有账号。恢复页介绍同步具体可浏览栏目，不新增解释性小字。

## Google后补时需要什么

基础Google身份登录的申请难度明显低于Apple：用户用自己的Google账号创建Cloud项目和Web客户端，填写品牌、支持邮箱、本站域名、隐私页和回调地址，完成平台要求的域名/品牌核验。我们只申请`openid/email/profile`，不索取Gmail或Drive权限。官方对仅基础身份范围有测试用户及授权期限的例外，但不能承诺所有账户免审或固定通过时长。来源：[Web配置](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)、[范围与发布状态](https://support.google.com/cloud/answer/15549945?hl=en)。

后续仍需实现服务器认证/回调，与原User/Session连接，按供应商稳定身份绑定，不能只凭相同邮箱静默合并账户。凭据经安全路径录入。此项C延期，不占首发阻塞；当前没有可用OAuth后端。

Apple本轮排除。开发者计划通常99美元/年（符合条件的机构可申请豁免），Web登录还需关联App ID/Services ID、配置域名/回调与签名私钥，官方环境要求涉及使用Apple登录的App Store应用。对目前纯网站首发不划算，不为登录另建应用。来源：[会员要求](https://developer.apple.com/programs/enroll/)、[登录环境](https://developer.apple.com/documentation/signinwithapple/configuring-your-environment-for-sign-in-with-apple)。

## 统一预览与公网边界

实际业务只使用`http://192.168.5.6:18084/`及其读者/管理路由，不新建平行网站。欢迎页保持独立，架构演示和旧布局比较工具不是业务版本。登录方式修改由共用AuthForm覆盖整页与弹窗。

公网前仍需选定并验证邮件服务、完成准确发布配置及同一时点文件/数据库备份恢复、核对最新生产账号与私人数据增量、核实外围网络并获得最终切换批准。私人研究中转由用户安全配置后才可实际调用。完整视觉验收依用户批注，不能声称全部像素一致或管理员业务试用已经通过。
