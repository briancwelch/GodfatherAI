import CommandCenter from "../../../components/command-center";
import { requireUser } from "../../../lib/control-server";
export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  await requireUser();
  return <CommandCenter initialWorkspace={(await params).id} />;
}
