<!-- 停靠栏外壳：模板页与导入页共用。类名取自模板页（单行高 53px，见 PageDrawer 的说明）。 -->
<template>
  <div
    class="sticky top-14 z-30 -mx-4 md:-mx-6 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 border-b px-4 md:px-6 py-2 flex flex-wrap items-center gap-2"
  >
    <slot />
  </div>
</template>
