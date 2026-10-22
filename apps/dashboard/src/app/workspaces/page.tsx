import WorkspaceDirectory from "../../components/workspace-directory";
import { requireUser } from "../../lib/control-server";
export default async function WorkspacesPage() {
  return <WorkspaceDirectory user={await requireUser()} />;
}
