<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useI18n } from "vue-i18n";
import { Plus } from "@lucide/vue";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import EmptyState from "@/components/EmptyState.vue";
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
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/errors";
import type { Datasource, DbType } from "@/lib/types";

defineProps<{ workspaceId: number | null }>();
const { t } = useI18n();

const datasources = ref<Datasource[]>([]);
const creating = ref(false);
const deleteOpen = ref(false);
const deleteTarget = ref<Datasource | null>(null);
const error = ref("");

const form = ref({
  name: "",
  db_type: "postgres" as DbType,
  host: "",
  port: 5432,
  database: "",
  username: "",
  password: "",
});

// 数据源是全局资源，由管理员维护，不属于某个工作区。
async function load(): Promise<void> {
  try {
    datasources.value = await api.get<Datasource[]>("/datasources");
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

onMounted(load);

async function create(): Promise<void> {
  error.value = "";
  try {
    await api.post("/datasources", form.value);
    creating.value = false;
    form.value = { name: "", db_type: "postgres", host: "", port: 5432, database: "", username: "", password: "" };
    await load();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function test(id: number): Promise<void> {
  error.value = "";
  try {
    await api.post(`/datasources/${id}/test`);
    toast.success(t("datasource.testOk"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

function openDelete(item: Datasource): void {
  deleteTarget.value = item;
  deleteOpen.value = true;
}

async function remove(): Promise<void> {
  if (deleteTarget.value == null) return;
  error.value = "";
  try {
    await api.delete(`/datasources/${deleteTarget.value.id}`);
    deleteOpen.value = false;
    await load();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('datasource.title')">
      <template #actions>
        <Dialog v-model:open="creating">
          <DialogTrigger as-child>
            <Button><Plus />{{ t("datasource.create") }}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{{ t("datasource.create") }}</DialogTitle>
            </DialogHeader>
            <form class="space-y-4" @submit.prevent="create">
              <div class="space-y-2">
                <Label for="ds-name">{{ t("common.name") }}</Label>
                <Input id="ds-name" v-model="form.name" required />
              </div>
              <div class="space-y-2">
                <Label>{{ t("datasource.title") }}</Label>
                <Select v-model="form.db_type">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="postgres">PostgreSQL</SelectItem>
                    <SelectItem value="mysql">MySQL</SelectItem>
                    <SelectItem value="dameng">达梦</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div class="grid grid-cols-[1fr_120px] gap-4">
                <div class="space-y-2">
                  <Label for="ds-host">{{ t("datasource.host") }}</Label>
                  <Input id="ds-host" v-model="form.host" required />
                </div>
                <div class="space-y-2">
                  <Label for="ds-port">{{ t("datasource.port") }}</Label>
                  <Input id="ds-port" v-model.number="form.port" type="number" />
                </div>
              </div>
              <div class="space-y-2">
                <Label for="ds-db">{{ t("datasource.database") }}</Label>
                <Input id="ds-db" v-model="form.database" required />
              </div>
              <div class="space-y-2">
                <Label for="ds-user">{{ t("datasource.username") }}</Label>
                <Input id="ds-user" v-model="form.username" required />
              </div>
              <div class="space-y-2">
                <Label for="ds-pass">{{ t("datasource.password") }}</Label>
                <Input id="ds-pass" v-model="form.password" type="password" required />
              </div>
              <DialogFooter>
                <Button type="submit">{{ t("common.save") }}</Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </template>
    </PageHeader>

    <Alert v-if="error" variant="destructive">
      <AlertDescription>{{ error }}</AlertDescription>
    </Alert>

    <EmptyState v-if="!datasources.length" :title="t('common.empty')" />
    <Table v-else>
      <TableBody>
        <TableRow v-for="item in datasources" :key="item.id">
          <TableCell class="font-medium">{{ item.name }}</TableCell>
          <TableCell class="text-muted-foreground">
            {{ item.db_type }} · {{ item.host }}:{{ item.port }}/{{ item.database }}
          </TableCell>
          <TableCell>
            <div class="flex justify-end gap-2">
              <Button variant="outline" size="sm" @click="test(item.id)">
                {{ t("datasource.test") }}
              </Button>
              <Button variant="outline" size="sm" @click="openDelete(item)">
                {{ t("common.delete") }}
              </Button>
            </div>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <AlertDialog v-model:open="deleteOpen">
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{{ t("common.confirmDelete") }}</AlertDialogTitle>
          <AlertDialogDescription>{{ deleteTarget?.name }}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{{ t("common.cancel") }}</AlertDialogCancel>
          <AlertDialogAction @click="remove">{{ t("common.delete") }}</AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  </div>
</template>
