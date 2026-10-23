# A coding project needs attention

Consigliere **0.9.0-rc.2** keeps your saved project configuration when a dependency
becomes unavailable. The worker connects for other enabled work
and excludes the affected project from coding and Apply jobs. The Connection tab
keeps a **PROJECT NEEDS ATTENTION** panel visible, including the project name,
problem and next steps. Open **Projects** and select an affected row for its full
message. A normal heartbeat does not dismiss this warning.

| Message                            | What to do                                                                                                                                                                                                               |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Saved Docker test image is missing | Restore the exact saved image shown in the message to your local Docker engine. Alternatively, remove and re-add the project in **Projects**, choosing an installed Linux test environment with the required test tools. |
| Local Docker is unavailable        | Open Docker Desktop or the local Docker engine and select the intended local context. Remote Docker endpoints are not accepted for coding.                                                                               |
| Docker is using Windows containers | Switch Docker Desktop to Linux containers.                                                                                                                                                                               |
| Test image is not a Linux image    | Remove and re-add the project using an installed Linux test environment.                                                                                                                                                 |
| Git is unavailable                 | Install or restore Git, then reopen Consigliere so it receives the updated command path.                                                                                                                                 |
| Project folder is unavailable      | Restore access to the saved folder, or remove and re-add the project using its correct location.                                                                                                                         |
| Dependency check timed out         | Check that the folder, Git and local Docker respond normally.                                                                                                                                                            |

After repair, **Pause**, then **Resume**. A successful check clears the warning
and republishes the original project if its saved configuration is unchanged.
Refresh the project selector in Command Center. Removing a project removes its
local worker grant only; it does not delete the project files. Re-adding creates
a new project grant and requires selecting its workspace, file scope, test
command and Apply permission again. Restore the original image to retain the
existing grant and job references.

Worker 0.9.0-rc.1 and earlier may stop with **Worker could not continue** for this
condition. While paused, restore the missing dependency or remove an unused
project, then Resume. Reconnecting the computer or reinstalling the same worker
does not restore a missing Docker image. Keep the existing connection and node
identity. No image downloads or permission changes happen automatically.

Updates preserve saved connections and project settings. An update restarts the
worker and therefore rechecks dependencies, which can expose an already missing
image. The owner confirmed Carbon's image had been removed by an earlier requested
cleanup; the restart exposed it. Before future Docker cleanup, preserve the exact
image pins in retained coding projects and data workload settings. A configured
test image may have no running container and still be required.

The Nodes heartbeat graph now keeps the actual timestamps observed while the
view is open for up to 60 seconds. A new receipt adds a pulse; old pulses scroll
left and leave the window. Refreshing the same timestamp adds nothing. Offline
and stale traces become muted while their observed history ages out. Reloading
or leaving the view starts a new observation window; no historic pulses are
invented or downloaded.

Implementation and release status are recorded separately in the verification
report; the currently published installer version remains listed in README.
