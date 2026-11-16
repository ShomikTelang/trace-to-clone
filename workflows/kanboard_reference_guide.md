# Reference workflow (recorded manually at first)

Run the official Kanboard container from `reference/compose.yml`. Create a disposable project named `Clone Research`, preferably with columns `Backlog`, `Ready`, `Work in progress`, `Done` (Kanboard's default column names may differ). This makes the reference comparison more meaningful.

Run `python -m traceclone login --url http://localhost:8081` and sign in, then:

```
python -m traceclone record --url http://localhost:8081 --headed --storage-state reference/storage-state.json --out artifacts/reference_trace
```

In the visible Kanboard browser, complete these actions. After each checkpoint, enter a short label in the recording terminal to capture a screenshot and DOM:

1. Open the project board. Record `board_initial`.
2. Click the plus icon in Backlog. Record `create_form`.
3. Create task `Fix authentication bug`, priority P0 if configured. Record `task_created`.
4. Open task details. Record `task_details`.
5. Move the task to `Work in progress`. Record `task_moved`.
6. Close the task. Record `task_closed`.
7. Type `done` in the terminal to finish.

Reference actions performed manually are captured as browser-level events on a best-effort basis and the screenshots/DOM are the primary evidence. The Playwright trace is most complete for *scripted* actions using the `--workflow` flag. Do not record personal accounts or sensitive content.

A fully automated reference flow should be produced after first observing and validating actual selectors. We deliberately do not ship untested selectors that would give false confidence.
