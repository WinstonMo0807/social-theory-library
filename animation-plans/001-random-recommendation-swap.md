# 001 — 为随机推荐增加局部换组动画

- **Status**: IMPLEMENTED 2026-07-29
- **Commit**: unversioned-workspace
- **Severity**: MEDIUM
- **Category**: Missed opportunities
- **Estimated scope**: 2 files, about 90 lines

## Problem

`web/components/random-recommendation.tsx:49` 直接递增偏移量：

```tsx
onClick={() => setOffset((value) => value + 1)}
```

推荐卡片随 React 更新瞬间替换。用户无法确认刷新是否生效，也没有局部状态反馈。整个页面不应重载，只应更换推荐内容。

## Target

把按钮与“换一组”文字放在同一个标题操作区。点击后仅对推荐图片、题名、作者、年份和阅读按钮执行一次短促的退出与进入过渡。

```css
:root {
  --ease-out: cubic-bezier(0.23, 1, 0.32, 1);
  --ease-in-out: cubic-bezier(0.77, 0, 0.175, 1);
}

.random-recommendation-content {
  opacity: 1;
  transform: translateY(0);
  filter: blur(0);
  transition:
    opacity 180ms var(--ease-out),
    transform 180ms var(--ease-out),
    filter 180ms var(--ease-out);
}

.random-recommendation-content[data-changing="true"] {
  opacity: 0;
  transform: translateY(6px);
  filter: blur(2px);
}
```

退出完成后更新资源，再进入。按钮保持可见，快速重复点击时不重载页面，也不累积定时器。动画只使用 `transform`、`opacity` 和低于 20px 的 `filter`。

## Repo conventions to follow

- 动效变量位于 `web/app/globals.css:3` 的 `:root`。
- 现有按钮按压反馈位于 `web/app/globals.css:178` 附近，使用 `transform: scale(0.97)`。
- 不增加动画库，继续使用 React 状态和 CSS transition。

## Steps

1. [x] 修改 `web/components/random-recommendation.tsx`，增加切换状态、当前推荐索引和可清理的定时器。
2. [x] 将推荐内容包进 `.random-recommendation-content`，按退出和进入阶段切换样式。
3. [x] 在标题右侧放置含刷新图标和“换一组”文字的按钮，并添加 `aria-live="polite"`。
4. [x] 修改 `web/app/globals.css`，加入局部过渡。
5. [x] 在减少动态效果模式下移除位移。

## Boundaries

- 不重新请求首页。
- 不调用 `window.location.reload()`。
- 不改变伪随机的用户种子规则。
- 不增加第三方动画依赖。

## Verification

- **Mechanical**: 在 `web` 目录运行 `npm.cmd test`，预期生产构建和渲染测试全部通过。
- **Feel check**:
  - 连续点击“换一组”，页面其他区域不得闪动或滚动。
  - 推荐内容先轻微下移淡出，再以新内容淡入，总时长不超过 360ms。
  - Chrome 动画面板 10% 速度下不得看到旧、新文字长时间重叠。
  - 开启 `prefers-reduced-motion` 后不得发生位移或模糊。
- **Done when**: 每次点击均更换馆藏资源，按钮状态清楚，动画只影响推荐卡片内容。
