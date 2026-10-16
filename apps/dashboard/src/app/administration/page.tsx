import Administration from "@/components/administration";
import { requireUser } from "@/lib/control-server";
export default async function AdministrationPage() {
  const user = await requireUser();
  return <Administration initialUser={user} />;
}
