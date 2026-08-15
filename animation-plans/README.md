# 动效实施计划

| 编号 | 标题 | 严重程度 | 状态 |
| --- | --- | --- | --- |
| 001 | 为随机推荐增加局部换组动画 | MEDIUM | IMPLEMENTED |
| 002 | 为前台页面切换增加克制的内容过渡 | MEDIUM | IMPLEMENTED |

建议先执行 001，再执行 002。两项共用全局 easing 变量，但彼此没有代码依赖。

审计同时发现 `web/app/globals.css` 中仍有 `padding` 和 `grid-template-columns` 的布局属性动画。它们不属于本次用户指定的核心场景，暂不扩大修改范围。后续如出现掉帧，再单独改为 `transform`。
