<script setup lang="ts">
import { ref } from "vue";
import { useI18n } from "vue-i18n";
import { Plus } from "@lucide/vue";
import { toast } from "vue-sonner";

import { api } from "@/api/client";
import PageHeader from "@/components/PageHeader.vue";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { errorMessage } from "@/lib/errors";
import type { Role, User } from "@/lib/types";
import { useSession } from "@/stores/session";

const { t } = useI18n();
const session = useSession();

const users = ref<User[]>([]);
const error = ref("");
const createOpen = ref(false);
const resetOpen = ref(false);
const resetTarget = ref<User | null>(null);
const resetPassword = ref("");
const form = ref({ username: "", password: "", role: "importer" as Role });

async function load(): Promise<void> {
  error.value = "";
  try {
    users.value = await api.get<User[]>("/users");
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function createUser(): Promise<void> {
  error.value = "";
  try {
    await api.post("/users", form.value);
    toast.success(t("users.created"));
    form.value = { username: "", password: "", role: "importer" };
    createOpen.value = false;
    await load();
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

async function updateUser(
  user: User,
  patch: { role?: Role; is_active?: boolean; password?: string },
  silent = false,
): Promise<void> {
  error.value = "";
  try {
    const updated = await api.put<User>(`/users/${user.id}`, patch);
    users.value = users.value.map((item) => (item.id === user.id ? updated : item));
    if (!silent) toast.success(t("users.updated"));
  } catch (caught) {
    error.value = errorMessage(caught);
  }
}

function openReset(user: User): void {
  resetTarget.value = user;
  resetPassword.value = "";
  error.value = "";
  resetOpen.value = true;
}

async function submitReset(): Promise<void> {
  if (resetPassword.value.length < 8) {
    error.value = t("auth.passwordTooShort");
    return;
  }
  if (resetTarget.value == null) return;
  await updateUser(resetTarget.value, { password: resetPassword.value }, true);
  resetOpen.value = false;
  toast.success(t("users.passwordReset"));
}

void load();
</script>

<template>
  <div class="space-y-6">
    <PageHeader :title="t('users.title')" :description="t('users.description')">
      <template #actions>
        <Dialog v-model:open="createOpen">
          <DialogTrigger as-child>
            <Button><Plus />{{ t("users.create") }}</Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>{{ t("users.create") }}</DialogTitle>
            </DialogHeader>
            <form class="space-y-4" @submit.prevent="createUser">
              <div class="space-y-2">
                <Label for="new-username">{{ t("auth.username") }}</Label>
                <Input id="new-username" v-model="form.username" required />
              </div>
              <div class="space-y-2">
                <Label for="new-password">{{ t("auth.password") }}</Label>
                <Input
                  id="new-password"
                  v-model="form.password"
                  type="password"
                  minlength="8"
                  required
                />
              </div>
              <div class="space-y-2">
                <Label>{{ t("admin.role") }}</Label>
                <Select v-model="form.role">
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="importer">{{ t("role.importer") }}</SelectItem>
                    <SelectItem value="admin">{{ t("role.admin") }}</SelectItem>
                  </SelectContent>
                </Select>
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
          <TableHead>{{ t("auth.username") }}</TableHead>
          <TableHead>{{ t("admin.role") }}</TableHead>
          <TableHead>{{ t("admin.active") }}</TableHead>
          <TableHead>{{ t("common.actions") }}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        <TableRow v-for="user in users" :key="user.id">
          <TableCell class="font-medium">{{ user.username }}</TableCell>
          <TableCell>
            <Select
              :model-value="user.role"
              :disabled="user.id === session.me?.id"
              @update:model-value="(value) => updateUser(user, { role: value as Role })"
            >
              <SelectTrigger class="w-28">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="importer">{{ t("role.importer") }}</SelectItem>
                <SelectItem value="admin">{{ t("role.admin") }}</SelectItem>
              </SelectContent>
            </Select>
          </TableCell>
          <TableCell>
            <Switch
              :model-value="user.is_active"
              :disabled="user.id === session.me?.id"
              @update:model-value="(value) => updateUser(user, { is_active: value === true })"
            />
          </TableCell>
          <TableCell>
            <Button variant="outline" size="sm" @click="openReset(user)">
              {{ t("users.resetPassword") }}
            </Button>
          </TableCell>
        </TableRow>
      </TableBody>
    </Table>

    <Dialog v-model:open="resetOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ t("users.resetTitle", { name: resetTarget?.username ?? "" }) }}</DialogTitle>
          <DialogDescription>{{ t("users.resetDesc") }}</DialogDescription>
        </DialogHeader>
        <div class="space-y-2">
          <Label for="reset-password">{{ t("users.newPassword") }}</Label>
          <Input
            id="reset-password"
            v-model="resetPassword"
            type="password"
            minlength="8"
            @keydown.enter="submitReset"
          />
        </div>
        <p v-if="error" class="text-sm text-destructive">{{ error }}</p>
        <DialogFooter>
          <Button variant="outline" @click="resetOpen = false">{{ t("common.cancel") }}</Button>
          <Button @click="submitReset">{{ t("common.save") }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>
