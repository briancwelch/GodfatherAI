import Administration from "@/components/administration";
import { requireUser } from "@/lib/control-server";
import { redirect } from "next/navigation";

export default async function AppearancePage() {
  const user = await requireUser();
  if (!user.permissions.includes("platform.manage"))
    redirect("/administration");
  return <Administration initialUser={user} initialTab="Appearance" />;
}
