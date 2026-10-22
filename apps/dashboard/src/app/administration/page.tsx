import Administration from "@/components/administration";
import { requireUser } from "@/lib/control-server";
import { redirect } from "next/navigation";
export default async function AdministrationPage() {
  const user = await requireUser();
  if (!user.permissions.includes("platform.manage")) redirect("/account");
  return <Administration initialUser={user} />;
}
