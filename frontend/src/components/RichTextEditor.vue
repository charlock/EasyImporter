<!-- 轻量富文本编辑器（Tiptap）：基础信息的说明字段用。
  支持加粗 / 斜体 / 删除线 / 标题 / 列表 / 链接 / 清除格式；内容以 HTML
  字符串双向绑定；只读时仍由编辑器渲染（contenteditable 关），不另写渲染分支。
  存入前由调用方按 HTML 字符串保存；加载时先过 sanitizeHtml 净化。 -->
<script setup lang="ts">
import { onBeforeUnmount, watch } from "vue";
import { useI18n } from "vue-i18n";
import { EditorContent, useEditor } from "@tiptap/vue-3";
import StarterKit from "@tiptap/starter-kit";
import Link from "@tiptap/extension-link";
import {
  Bold,
  Heading1,
  Heading2,
  Italic,
  Link2,
  List,
  ListOrdered,
  RemoveFormatting,
  Strikethrough,
} from "@lucide/vue";

import { Button } from "@/components/ui/button";
import { sanitizeHtml } from "@/lib/richText";

const props = withDefaults(
  defineProps<{ modelValue: string; editable?: boolean }>(),
  { editable: true },
);
const emit = defineEmits<{ "update:modelValue": [value: string] }>();
const { t } = useI18n();

const editor = useEditor({
  content: sanitizeHtml(props.modelValue),
  editable: props.editable,
  extensions: [
    StarterKit,
    Link.configure({
      openOnClick: false,
      HTMLAttributes: { target: "_blank", rel: "noopener noreferrer" },
    }),
  ],
  onUpdate: ({ editor: current }) => {
    emit("update:modelValue", current.getHTML());
  },
});

/** 外部改值（切换模板 / 取消编辑回填）时同步进编辑器；编辑器自身的
 * onUpdate 回写不触发本 watcher（modelValue 已是同一值时跳过）。 */
watch(
  () => props.modelValue,
  (value) => {
    const current = editor.value;
    if (!current) return;
    const clean = sanitizeHtml(value);
    if (current.getHTML() !== clean) current.commands.setContent(clean);
  },
);
watch(
  () => props.editable,
  (editable) => editor.value?.setEditable(editable),
);
onBeforeUnmount(() => editor.value?.destroy());

/** 链接：已有链接时点按取消；否则弹输入框要网址，留空则不设链接。 */
function toggleLink(): void {
  const current = editor.value;
  if (!current) return;
  if (current.isActive("link")) {
    current.chain().focus().unsetLink().run();
    return;
  }
  const href = window.prompt(t("richtext.linkPrompt"), current.getAttributes("link").href ?? "");
  if (href == null || href.trim() === "") return;
  current.chain().focus().setLink({ href: href.trim() }).run();
}
</script>

<template>
  <div class="rounded-md border">
    <div v-if="editable" class="flex flex-wrap items-center gap-0.5 border-b p-1">
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('bold') ? 'bg-accent' : ''"
        :title="t('richtext.bold')" @click="editor?.chain().focus().toggleBold().run()"
      >
        <Bold class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('italic') ? 'bg-accent' : ''"
        :title="t('richtext.italic')" @click="editor?.chain().focus().toggleItalic().run()"
      >
        <Italic class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('strike') ? 'bg-accent' : ''"
        :title="t('richtext.strike')" @click="editor?.chain().focus().toggleStrike().run()"
      >
        <Strikethrough class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('heading', { level: 1 }) ? 'bg-accent' : ''"
        :title="t('richtext.heading1')" @click="editor?.chain().focus().toggleHeading({ level: 1 }).run()"
      >
        <Heading1 class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('heading', { level: 2 }) ? 'bg-accent' : ''"
        :title="t('richtext.heading2')" @click="editor?.chain().focus().toggleHeading({ level: 2 }).run()"
      >
        <Heading2 class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('bulletList') ? 'bg-accent' : ''"
        :title="t('richtext.bulletList')" @click="editor?.chain().focus().toggleBulletList().run()"
      >
        <List class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('orderedList') ? 'bg-accent' : ''"
        :title="t('richtext.orderedList')" @click="editor?.chain().focus().toggleOrderedList().run()"
      >
        <ListOrdered class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :class="editor?.isActive('link') ? 'bg-accent' : ''"
        :title="t('richtext.link')"
        @click="toggleLink()"
      >
        <Link2 class="h-4 w-4" />
      </Button>
      <Button
        variant="ghost" size="sm" class="h-7 px-2"
        :title="t('richtext.clearFormatting')" @click="editor?.chain().focus().clearNodes().unsetAllMarks().run()"
      >
        <RemoveFormatting class="h-4 w-4" />
      </Button>
    </div>
    <EditorContent :editor="editor" class="rich-text-content min-h-24 px-3 py-2 text-sm" />
  </div>
</template>

<style scoped>
/* Tailwind preflight 会清掉标题/列表的默认样式，这里给编辑器内容补回最小排版，
 * 与说明字段“常用格式即可”的定位一致。 */
.rich-text-content :deep(h1) {
  font-size: 1.125rem;
  font-weight: 600;
  margin: 0.25rem 0;
}
.rich-text-content :deep(h2) {
  font-size: 1rem;
  font-weight: 600;
  margin: 0.25rem 0;
}
.rich-text-content :deep(p) {
  margin: 0.25rem 0;
}
.rich-text-content :deep(ul) {
  list-style: disc;
  padding-left: 1.25rem;
  margin: 0.25rem 0;
}
.rich-text-content :deep(ol) {
  list-style: decimal;
  padding-left: 1.25rem;
  margin: 0.25rem 0;
}
.rich-text-content :deep(a) {
  color: var(--primary);
  text-decoration: underline;
}
.rich-text-content :deep(.tiptap) {
  outline: none;
}
.rich-text-content :deep(.tiptap p.is-editor-empty:first-child::before) {
  color: var(--muted-foreground);
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
}
</style>
