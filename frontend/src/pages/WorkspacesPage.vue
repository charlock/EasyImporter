<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useI18n } from "vue-i18n";
import { Pencil, Plus, Trash2 } from "@lucide/vue";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import { errorMessage } from "@/lib/errors";
import type { User, Workspace } from "@/lib/types";
import { useSession } from "@/stores/session";

const { t } = useI18n();
const session = useSession();

const users = ref<User[]>([]);
const error = ref("");
const createOpen = ref(false);
const renameOpen = ref(false);
const deleteOpen = ref(false);
const renameTarget = ref<Workspace | null>(null);
const deleteTarget = ref<Workspace | null>(null);
const createForm = ref({ name: "", description: "" });
const renameForm = ref({ name: "", description: "" });

const memberWorkspaceId = ref<number | null>(session.workspaces[0]?.id ?? null);
const memberIds = ref<Set<number>>(new Set());

const importers = computed(() => users.value.filter((user) => user.role !== "admin"));

async function loadUsers(): Promise<void> {
  try {
    users.value = await api.get<User[]>("/users");
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function createWorkspace(): Promise<void> {
  error.value = "";
  try {
    const workspace = await api.post<Workspace>("/workspaces", createForm.value);
    session.workspaces = [...session.workspaces, workspace];
    memberWorkspaceId.value ??= workspace.id;
    createForm.value = { name: "", description: "" };
    createOpen.value = false;
    toast.success(t("workspaces.created"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

function openRename(item: Workspace): void {
  renameTarget.value = item;
  renameForm.value = { name: item.name, description: item.description };
  renameOpen.value = true;
}

async function submitRename(): Promise<void> {
  if (renameTarget.value == null) return;
  error.value = "";
  try {
    const updated = await api.put<Workspace>(`/workspaces/${renameTarget.value.id}`, renameForm.value);
    session.workspaces = session.workspaces.map((item) => (item.id === updated.id ? updated : item));
    renameOpen.value = false;
    toast.success(t("workspaces.renamed"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

function openDelete(item: Workspace): void {
  deleteTarget.value = item;
  deleteOpen.value = true;
}

async function submitDelete(): Promise<void> {
  if (deleteTarget.value == null) return;
  error.value = "";
  try {
    await api.delete(`/workspaces/${deleteTarget.value.id}`);
    session.workspaces = session.workspaces.filter((item) => item.id !== deleteTarget.value?.id);
    if (memberWorkspaceId.value === deleteTarget.value.id) {
      memberWorkspaceId.value = session.workspaces[0]?.id ?? null;
    }
    deleteOpen.value = false;
    toast.success(t("workspaces.deleted"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

watch(
  memberWorkspaceId,
  async (id) => {
    memberIds.value = new Set();
    if (id == null) return;
    try {
      const members = await api.get<User[]>(`/workspaces/${id}/members`);
      memberIds.value = new Set(members.map((user) => user.id));
    } catch (caught) {
      error.value = errorMessage(caught);
    }
  },
  { immediate: true },
);

function toggleMember(id: number, checked: boolean | "indeterminate"): void {
  const next = new Set(memberIds.value);
  if (checked === true) next.add(id);
  else next.delete(id);
  memberIds.value = next;
}

async function saveMembers(): Promise<void> {
  if (memberWorkspaceId.value == null) return;
  error.value = "";
  try {
    const members = await api.put<User[]>(`/workspaces/${memberWorkspaceId.value}/members`, {
      user_ids: [...memberIds.value],
    });
    memberIds.value = new Set(members.map((user) => user.id));
    session.workspaces = session.workspaces.map((item) =>
      item.id === memberWorkspaceId.value ? { ...item, member_count: members.length } : item,
    );
    toast.success(t("workspaces.saved"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

void loadUsers();
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('workspaces.title')" :description="t('workspaces.description')">
      <template #actions>
        <Dialog v-model:open="createOpen">
          <DialogTrigger as-child>
            <Button><Plus />{{ t("workspaces.create") }}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{{ t("workspaces.create") }}</DialogTitle>
            </DialogHeader>
            <form class="space-y-4" @submit.prevent="createWorkspace">
              <div class="space-y-2">
                <Label for="ws-name">{{ t("common.name") }}</Label>
                <Input id="ws-name" v-model="createForm.name" required />
              </div>
              <div class="space-y-2">
                <Label for="ws-desc">{{ t("common.description") }}</Label>
                <Input id="ws-desc" v-model="createForm.description" />
              </div>
              <DialogFooter>
                <Button type="submit">{{ t("common.create") }}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{{ t("common.name") }}</TableHead>
          <TableHead>{{ t("common.description") }}</TableHead>
          <TableHead>{{ t("workspaces.members") }}</TableHead>
          <TableHead>{{ t("common.actions") }}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-for="item in session.workspaces" :key="item.id">
          <TableCell class="font-medium">{{ item.name }}</TableCell>
          <TableCell class="text-muted-foreground">{{ item.description }}</TableCell>
          <TableCell>{{ t("workspaces.memberCount", { n: item.member_count }) }}</TableCell>
          <TableCell>
            <div class="flex gap-2">
              <Button variant="outline" size="sm" @click="openRename(item)">
                <Pencil />{{ t("workspaces.rename") }}
              </Button>
              <Button variant="outline" size="sm" @click="openDelete(item)">
                <Trash2 />{{ t("common.delete") }}
              </Button>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <Card>
      <CardHeader>
        <CardTitle>{{ t("workspaces.members") }}</CardTitle>
        <CardDescription>{{ t("workspaces.membersDesc") }}</CardDescription>
      </CardHeader>
      <CardContent class="space-y-4">
        <Select
          :model-value="memberWorkspaceId == null ? undefined : String(memberWorkspaceId)"
          @update:model-value="(value) => (memberWorkspaceId = value == null ? null : Number(value))"
        >
          <SelectTrigger class="w-64">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem
              v-for="item in session.workspaces"
              :key="item.id"
              :value="String(item.id)"
            >
              {{ item.name }}
            </SelectItem>
          </SelectContent>
        </Select>
        <div class="flex flex-wrap gap-x-4 gap-y-2">
          <label
            v-for="user in importers"
            :key="user.id"
            class="flex items-center gap-2 text-sm"
          >
            <Checkbox
              :model-value="memberIds.has(user.id)"
              @update:model-value="(value) => toggleMember(user.id, value)"
            />
            {{ user.username }}
          </label>
        </div>
        <Button :disabled="memberWorkspaceId == null" @click="saveMembers">
          {{ t("workspaces.saved") }}
        </Button>
      </CardContent>
    </Card>

    <Dialog v-model:open="renameOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t("workspaces.rename") }}</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="rename-name">{{ t("common.name") }}</Label>
            <Input id="rename-name" v-model="renameForm.name" required />
          </div>
          <div class="space-y-2">
            <Label for="rename-desc">{{ t("common.description") }}</Label>
            <Input id="rename-desc" v-model="renameForm.description" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" @click="renameOpen = false">{{ t("common.cancel") }}</Button>
          <Button @click="submitRename">{{ t("common.save") }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <AlertDialog v-model:open="deleteOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t("workspaces.deleteTitle") }}</AlertDialogTitle>
          <AlertDialogDescription>{{ t("workspaces.deleteDesc") }}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction @click="submitDelete">{{ t("common.delete") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
