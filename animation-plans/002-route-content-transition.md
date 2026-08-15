# 002 — 为前台页面切换增加克制的内容过渡

- **Status**: IMPLEMENTED 2026-07-29
- **Commit**: unversioned-workspace
- **Severity**: MEDIUM
- **Category**: Missed opportunities
- **Estimated scope**: 3 files, about 80 lines

## Problem

`web/app/layout.tsx:44` 直接渲染页面内容：

```tsx
<main id="main-content">{children}</main>
```

导航切换没有局部状态提示。较慢请求时，用户会把内容瞬间替换误认为整页刷新。管理后台和阅读器属于高频工作区域，不适合加入明显位移。

## Target

新增客户端 `RouteTransition` 包装器。仅在前台内容区域按路径变化执行 180ms 的透明度与 8px 纵向位移。后台和阅读器只保留透明度，避免高频工作时拖慢操作。

```css
.route-transition {
  opacity: 1;
  transform: translateY(0);
  transition:
    opacity 180ms var(--ease-out),
    transform 180ms var(--ease-out);
}

.route-transition[data-entering="true"] {
  opacity: 0;
  transform: translateY(8px);
}

@media (prefers-reduced-motion: reduce) {
  .route-transition {
    transform: none;
    transition: opacity 120ms ease;
  }
}
```

进入动效采用 `cubic-bezier(0.23, 1, 0.32, 1)`。不得拦截导航，也不得延迟链接响应。

## Repo conventions to follow

- `web/components/site-header.tsx:31` 已使用 `usePathname()` 判断当前路径。
- 全局动效变量位于 `web/app/globals.css:3`。
- 前台保持黑白、低对比度位移。后台和阅读器保持更快、更少的运动。

## Steps

1. [x] 新建 `web/components/route-transition.tsx`，按路径变化执行可取消的 Web Animation。
2. [x] 新动画启动时自动取代旧动画，防止快速切换时累积。
3. [x] 在 `web/app/layout.tsx` 中用 `RouteTransition` 包裹 `children`。
4. [x] 动画采用 220ms 透明度与 8px 位移，并尊重减少动态效果设置。
5. [x] 后台只动画 `.admin-content`，阅读器只动画文档区域。

## Boundaries

- 不拦截 Next.js Link。
- 不等待退出动画后再开始导航。
- 不使用 View Transition API 作为唯一实现，保持现有浏览器兼容性。
- 不对键盘导航增加额外等待。

## Verification

- **Mechanical**: 在 `web` 目录运行 `npm.cmd test` 和 `npm.cmd run lint`。
- **Feel check**:
  - 首页进入学者、主题、理论流派和作品次级页时，内容变化清楚但不拖沓。
  - 快速连续点击导航时，动画可以被下一次状态覆盖，不从零重新排队。
  - 管理后台切换功能页时没有明显滑动。
  - 开启 `prefers-reduced-motion` 后只剩短促透明度反馈。
- **Done when**: 前台页面切换可感知，导航仍即时响应，后台和阅读器没有多余运动。
