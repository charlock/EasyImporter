<!-- 通用列表页壳：参考 studio-admin tasks 页。
  头部（标题+描述+右上操作）/ 过滤行（搜索 + 各页自定义过滤）/ 数据表 /
  底部（已选行数 + 每页行数 + 数字分页）。
  列由 ListColumn 定义：kind 决定唯一的单元格表达（link/badge/text/meta/count），
  actions 列由 actions prop 提供统一的行操作菜单；同一列内不再混用两种渲染。 -->
<script setup lang="ts" generic="T">
import { computed } from "vue";
import { useI18n } from "vue-i18n";
import { MoreHorizontal, Search } from "@lucide/vue";

import EmptyState from "@/components/EmptyState.vue";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  badgeToneClass,
  pageNumbers,
  type ListAction,
  type ListCellValue,
  type ListColumn,
} from "./listTypes";

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    columns: ListColumn<T>[];
    rows: T[];
    rowKey: (row: T) => number;
    /** 总行数（服务端分页用服务端总数，客户端分页用过滤后总数）。 */
    total: number;
    selectable?: boolean;
    actions?: (row: T) => ListAction[];
    error?: string;
    showSearch?: boolean;
    searchPlaceholder?: string;
    emptyTitle?: string;
    pageSizes?: number[];
  }>(),
  { selectable: true, pageSizes: () => [10, 20, 50] },
);

const page = defineModel<number>("page", { required: true });
const pageSize = defineModel<number>("pageSize", { required: true });
const search = defineModel<string>("search", { default: "" });
const selected = defineModel<Set<number>>("selected", { required: true });

const { t } = useI18n();

const totalPages = computed(() => Math.max(1, Math.ceil(props.total / pageSize.value)));
const pages = computed(() => pageNumbers(page.value, totalPages.value));
const allSelected = computed(
  () => props.rows.length > 0 && props.rows.every((row) => selected.value.has(props.rowKey(row))),
);
const someSelected = computed(() => props.rows.some((row) => selected.value.has(props.rowKey(row))));

function toggleAll(checked: boolean | "indeterminate"): void {
  selected.value =
    checked === true ? new Set(props.rows.map((row) => props.rowKey(row))) : new Set();
}

function toggleOne(id: number, checked: boolean | "indeterminate"): void {
  const next = new Set(selected.value);
  if (checked === true) next.add(id);
  else next.delete(id);
  selected.value = next;
}

function onPageSize(value: unknown): void {
  if (typeof value !== "string") return;
  pageSize.value = Number(value);
  page.value = 1;
}

function cellSub(value: ListCellValue): string[] {
  if (value.type === "link") return value.sub ?? [];
  return [];
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="title" :description="description">
      <template #actions><slot name="actions" /></template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <!-- 过滤行：搜索 + 各页自定义过滤（tasks 页的 Status / Priority 下拉同款位置） -->
    <div class="flex flex-wrap items-center gap-2">
      <div v-if="showSearch" class="relative w-64">
        <Search class="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input v-model="search" class="pl-8" :placeholder="searchPlaceholder ?? t('common.search')" />
      </div>
      <slot name="filters" />
    </div>

    <p v-if="selected.size" class="text-sm text-muted-foreground">
      {{ t("list.selectedOf", { selected: selected.size, total }) }}
    </p>

    <EmptyState v-if="!rows.length" :title="emptyTitle ?? t('common.empty')" />
    <template v-else>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead v-if="selectable" class="w-10">
              <Checkbox
                :checked="allSelected ? true : someSelected ? 'indeterminate' : false"
                :aria-label="t('list.selectedOf', { selected: selected.size, total })"
                @update:checked="toggleAll"
              />
            </TableHead>
            <TableHead
              v-for="column in columns"
              :key="column.key"
              :class="[column.kind === 'actions' ? 'w-[70px] text-right' : '', column.headerClass]"
            >
              {{ column.header }}
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          <TableRow
            v-for="row in rows"
            :key="rowKey(row)"
            :data-state="selected.has(rowKey(row)) ? 'selected' : undefined"
          >
            <TableCell v-if="selectable">
              <Checkbox
                :checked="selected.has(rowKey(row))"
                :aria-label="`#${rowKey(row)}`"
                @update:checked="(checked: boolean | 'indeterminate') => toggleOne(rowKey(row), checked)"
              />
            </TableCell>
            <template v-for="column in columns" :key="column.key">
              <TableCell v-if="column.kind === 'actions'" class="text-right">
                <DropdownMenu v-if="actions">
                  <DropdownMenuTrigger as-child>
                    <Button variant="ghost" size="icon" class="h-8 w-8">
                      <MoreHorizontal class="h-4 w-4" />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem
                      v-for="(action, index) in actions(row)"
                      :key="index"
                      :class="action.danger ? 'text-destructive' : ''"
                      :disabled="action.disabled"
                      :title="action.title"
                      @click="action.onClick()"
                    >
                      <component :is="action.icon" v-if="action.icon" class="mr-2 h-4 w-4" />
                      {{ action.label }}
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
              <TableCell v-else-if="column.kind === 'link'" :class="column.class">
                <RouterLink :to="column.cell(row).to" class="font-medium hover:underline">
                  {{ column.cell(row).label }}
                </RouterLink>
                <p
                  v-for="(line, index) in cellSub(column.cell(row))"
                  :key="index"
                  class="truncate text-sm text-muted-foreground"
                  :class="index === 0 ? '' : 'text-xs'"
                >
                  {{ line }}
                </p>
              </TableCell>
              <TableCell v-else-if="column.kind === 'badge'" :class="column.class">
                <Badge variant="outline" :class="badgeToneClass[column.cell(row).tone]">
                  {{ column.cell(row).label }}
                </Badge>
              </TableCell>
              <TableCell v-else-if="column.kind === 'count'" :class="column.class">
                {{ column.cell(row).primary }}
                <span
                  v-if="column.cell(row).secondary"
                  :class="column.cell(row).danger ? 'text-destructive' : 'text-muted-foreground'"
                >
                  · {{ column.cell(row).secondary }}
                </span>
              </TableCell>
              <TableCell v-else-if="column.kind === 'meta'" :class="column.class">
                {{ column.cell(row).primary }}
                <span v-if="column.cell(row).secondary" class="block text-xs text-muted-foreground">
                  {{ column.cell(row).secondary }}
                </span>
              </TableCell>
              <TableCell v-else :class="column.class">
                {{ column.cell(row).text }}
                <span v-if="column.cell(row).sub" class="block text-xs text-muted-foreground">
                  {{ column.cell(row).sub }}
                </span>
              </TableCell>
            </template>
          </TableRow>
        </TableBody>
      </Table>

      <!-- 底部：每页行数 + 数字分页（tasks 页同款：Prev / 页码 / Next + 第 x / y 页） -->
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2 text-sm text-muted-foreground">
          <span>{{ t("list.rowsPerPage") }}</span>
          <Select :model-value="String(pageSize)" @update:model-value="onPageSize">
            <SelectTrigger class="h-8 w-20"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem v-for="size in pageSizes" :key="size" :value="String(size)">
                {{ size }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div class="flex items-center gap-1">
          <Button variant="outline" size="sm" :disabled="page <= 1" @click="page -= 1">
            {{ t("common.prev") }}
          </Button>
          <template v-for="(item, index) in pages" :key="index">
            <span v-if="item === '…'" class="px-1 text-sm text-muted-foreground">…</span>
            <Button
              v-else
              variant="outline"
              size="sm"
              :class="item === page ? 'bg-accent' : ''"
              @click="page = item"
            >
              {{ item }}
            </Button>
          </template>
          <Button variant="outline" size="sm" :disabled="page >= totalPages" @click="page += 1">
            {{ t("common.next") }}
          </Button>
        </div>
        <span class="text-sm text-muted-foreground">
          {{ t("list.pageOf", { page, pages: totalPages }) }}
        </span>
      </div>
    </template>
  </div>
</template>
