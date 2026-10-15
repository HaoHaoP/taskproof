import { d as defineComponent, c as createElementBlock, F as Fragment, y as createTextVNode, t as toDisplayString, h as computed, o as openBlock, V as metaFor, _ as _export_sfc, i as useBoardStore, u as useI18n, k as watch, W as onBeforeUnmount, x as createBlock, l as withCtx, f as unref, U as ref, p as resolveComponent, b as createBaseVNode, e as createVNode, w as withKeys, a as withModifiers, n as normalizeClass, X as withDirectives, Y as vShow, r as renderList, g as createCommentVNode, Z as formatBytes, $ as byteLength, a0 as LOG_MAX_LINES, a1 as highlightSegments, a2 as shouldStickBottom, a3 as nextTick, s as useRoute, v as useRouter, a4 as ABNORMAL, a5 as countMatches, a6 as matchLineIndexes, a7 as stripAnsi } from "./index-Cd1EoUu-.js";
const _hoisted_1$1 = ["data-status", "data-shape"];
const _hoisted_2$1 = {
  key: 0,
  class: "dot"
};
const _sfc_main$1 = /* @__PURE__ */ defineComponent({
  __name: "StatusMark",
  props: {
    status: {},
    shape: { default: "glyph" }
  },
  setup(__props) {
    const props = __props;
    const meta = computed(() => metaFor(props.status));
    return (_ctx, _cache) => {
      return openBlock(), createElementBlock("span", {
        class: "tp-mark",
        "data-status": meta.value.id,
        "data-shape": __props.shape
      }, [
        __props.shape === "dot" ? (openBlock(), createElementBlock("span", _hoisted_2$1)) : (openBlock(), createElementBlock(Fragment, { key: 1 }, [
          createTextVNode(toDisplayString(meta.value.glyph), 1)
        ], 64))
      ], 8, _hoisted_1$1);
    };
  }
});
const StatusMark = /* @__PURE__ */ _export_sfc(_sfc_main$1, [["__scopeId", "data-v-7a91d873"]]);
function shortTime(value) {
  if (!value) return "—";
  const match = value.match(/T(\d{2}:\d{2}:\d{2})/);
  return match ? match[1] : value;
}
function duration(startedAt, finishedAt) {
  if (!startedAt) return "—";
  const start = Date.parse(startedAt);
  const end = finishedAt ? Date.parse(finishedAt) : Date.now();
  if (Number.isNaN(start) || Number.isNaN(end)) return "—";
  const total = Math.max(0, Math.round((end - start) / 1e3));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}m${String(seconds).padStart(2, "0")}s`;
}
function payloadLine(payload) {
  if (payload == null) return "";
  if (typeof payload !== "object") return String(payload);
  const parts = [];
  for (const [key, value] of Object.entries(payload)) {
    if (value === null || value === void 0 || value === "") continue;
    if (Array.isArray(value)) {
      parts.push(`${key} ${value.length}`);
    } else if (typeof value === "object") {
      parts.push(`${key} {...}`);
    } else {
      parts.push(`${key} ${String(value)}`);
    }
  }
  return parts.join(" · ");
}
function eventSummary(name, payload) {
  const p = payload ?? {};
  const cap = (value, limit = 160) => value.length > limit ? `${value.slice(0, limit)}…` : value;
  switch (name) {
    case "started":
      return [p.adapter, p.group, p.worktree ? "worktree" : null].filter(Boolean).join(" · ");
    case "result_schema":
      if (p.enabled === false) return "off";
      return String(p.path ?? "").split("/").pop() || "—";
    case "adapter":
      return [
        p.exit_code != null ? `exit ${p.exit_code}` : null,
        p.degraded ? "degraded" : null
      ].filter(Boolean).join(" · ");
    case "verify":
      return [p.status, p.exit_code != null ? `exit ${p.exit_code}` : null].filter(Boolean).join(" · ");
    case "done":
      return [p.verify, p.files_changed != null ? String(p.files_changed) : null].filter(Boolean).join(" · ");
    case "failed":
      return cap(String(p.reason ?? p.stage ?? payloadLine(payload)));
    case "forbidden": {
      const paths = Array.isArray(p.paths) ? p.paths.join(", ") : "";
      return cap(paths || payloadLine(payload));
    }
    default:
      return cap(payloadLine(payload));
  }
}
function isBadEvent(name, payload) {
  const p = payload ?? {};
  if (["failed", "forbidden", "blocked", "timeout", "cancelled"].includes(name)) return true;
  if (name === "verify") return p.status === "FAILED";
  if (name === "adapter") return typeof p.exit_code === "number" && p.exit_code !== 0;
  return false;
}
const DRAWER_MOUNT_RETRIES = 3;
function shouldRetryDrawerMount(state, retries = DRAWER_MOUNT_RETRIES) {
  return state.open && !state.mounted && state.attempt < retries;
}
function drawerMountKey(attempt) {
  return `drawer-${attempt}`;
}
const _hoisted_1 = { class: "dh" };
const _hoisted_2 = ["data-status"];
const _hoisted_3 = { class: "cid" };
const _hoisted_4 = { class: "dur" };
const _hoisted_5 = ["aria-label"];
const _hoisted_6 = {
  class: "dtabs",
  role: "tablist"
};
const _hoisted_7 = ["aria-selected"];
const _hoisted_8 = ["aria-selected"];
const _hoisted_9 = { class: "dbody" };
const _hoisted_10 = { class: "sec" };
const _hoisted_11 = { class: "full" };
const _hoisted_12 = { class: "sec" };
const _hoisted_13 = ["data-off"];
const _hoisted_14 = { class: "tl" };
const _hoisted_15 = { class: "t" };
const _hoisted_16 = { class: "k" };
const _hoisted_17 = { class: "g" };
const _hoisted_18 = {
  key: 0,
  class: "d"
};
const _hoisted_19 = {
  key: 0,
  class: "ev"
};
const _hoisted_20 = {
  key: 0,
  class: "sec"
};
const _hoisted_21 = { class: "vrow" };
const _hoisted_22 = { class: "vlabel" };
const _hoisted_23 = {
  key: 0,
  class: "vcmd"
};
const _hoisted_24 = {
  key: 0,
  class: "side claim"
};
const _hoisted_25 = { class: "body" };
const _hoisted_26 = {
  key: 1,
  class: "rule"
};
const _hoisted_27 = { class: "side ev" };
const _hoisted_28 = { class: "logpanel" };
const _hoisted_29 = { class: "logbar" };
const _hoisted_30 = ["value", "placeholder", "aria-label"];
const _hoisted_31 = { class: "logcount" };
const _hoisted_32 = ["aria-label", "disabled"];
const _hoisted_33 = ["aria-label", "disabled"];
const _hoisted_34 = { class: "logscope" };
const _hoisted_35 = {
  key: 0,
  class: "lognone"
};
const _hoisted_36 = {
  key: 0,
  class: "lognote"
};
const _hoisted_37 = {
  key: 1,
  class: "lognote"
};
const _hoisted_38 = {
  key: 2,
  class: "logerr"
};
const _hoisted_39 = {
  key: 0,
  class: "logempty"
};
const _hoisted_40 = ["data-line"];
const _hoisted_41 = {
  key: 1,
  class: "none"
};
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "TaskDrawer",
  setup(__props) {
    const store = useBoardStore();
    const route = useRoute();
    const router = useRouter();
    const { t, te } = useI18n();
    const open = computed(() => typeof route.params.taskId === "string" && route.params.taskId !== "");
    const task = computed(() => store.detail?.task ?? null);
    const events = computed(() => store.detail?.events ?? []);
    const tab = computed(() => route.query.tab === "log" ? "log" : "overview");
    const liveTask = computed(() => {
      const status = task.value?.status;
      return store.polling && (status === "running" || status === "verifying");
    });
    const timeline = computed(
      () => events.value.map((event) => ({
        t: shortTime(event.ts),
        k: te(`event.${event.event}`) ? t(`event.${event.event}`) : event.event,
        g: event.event === "adapter" || event.event === "verify" ? "" : "",
        d: eventSummary(event.event, event.payload),
        bad: isBadEvent(event.event, event.payload)
      }))
    );
    const verify = computed(() => task.value?.verify_exit ?? null);
    const verifyText = computed(
      () => verify.value == null ? t("ev.notrun") : `exit ${verify.value}`
    );
    const dur = computed(() => duration(task.value?.started_at ?? null, task.value?.finished_at ?? null));
    const started = computed(() => shortTime(task.value?.started_at));
    const ended = computed(() => task.value?.finished_at ? shortTime(task.value.finished_at) : t("drawer.now"));
    function close() {
      const name = typeof route.name === "string" ? route.name : "matrix";
      void router.push({ name, query: route.query });
    }
    function go(nextTab) {
      const name = typeof route.name === "string" ? route.name : "matrix";
      const id = typeof route.params.taskId === "string" ? route.params.taskId : "";
      const query2 = { ...route.query };
      if (nextTab === "log") query2.tab = "log";
      else delete query2.tab;
      void router.push({ name, params: { taskId: id }, query: query2 });
    }
    function onVisible(value) {
      if (!value) close();
    }
    const showClaim = computed(() => ABNORMAL.includes(task.value?.status ?? ""));
    const logDisplay = computed(() => stripAnsi(store.logText));
    const logLines = computed(() => logDisplay.value === "" ? [] : logDisplay.value.split("\n"));
    const query = ref("");
    const matchCount = computed(() => countMatches(logDisplay.value, query.value));
    const hitLines = computed(() => matchLineIndexes(logDisplay.value, query.value));
    const currentHit = ref(0);
    const hitPosition = computed(() => matchCount.value ? currentHit.value + 1 : 0);
    watch(query, () => currentHit.value = 0);
    const logEl = ref(null);
    const stuck = ref(true);
    const newLines = ref(0);
    function onLogScroll() {
      const el = logEl.value;
      if (!el) return;
      if (shouldStickBottom(el.scrollTop, el.scrollHeight, el.clientHeight)) {
        stuck.value = true;
        newLines.value = 0;
      } else {
        stuck.value = false;
      }
    }
    function scrollToBottom() {
      const el = logEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    }
    watch(
      () => logDisplay.value,
      async (now, before) => {
        if (before === void 0 || now === before) return;
        const beforeLines = before === "" ? 0 : before.split("\n").length;
        const afterLines = logLines.value.length;
        await nextTick();
        if (stuck.value) scrollToBottom();
        else if (afterLines > beforeLines) newLines.value += afterLines - beforeLines;
      }
    );
    watch(
      () => store.logTaskId,
      () => {
        stuck.value = true;
        newLines.value = 0;
        query.value = "";
        void nextTick(scrollToBottom);
      }
    );
    function jumpBottom() {
      stuck.value = true;
      newLines.value = 0;
      scrollToBottom();
      void nextTick(scrollToBottom);
    }
    function isCurrentHitLine(index) {
      return hitLines.value[currentHit.value] === index;
    }
    function scrollHitIntoView() {
      const el = logEl.value;
      const line = hitLines.value[currentHit.value];
      if (!el || line == null) return;
      const target = el.querySelector(`[data-line="${line}"]`);
      if (!target) return;
      const delta = target.getBoundingClientRect().top - el.getBoundingClientRect().top;
      el.scrollTop += delta - el.clientHeight / 2 + target.clientHeight / 2;
    }
    function goToHit(index) {
      const total = hitLines.value.length;
      if (!total) return;
      currentHit.value = (index % total + total) % total;
      void nextTick(scrollHitIntoView);
    }
    function nextHit() {
      goToHit(currentHit.value + 1);
    }
    function prevHit() {
      goToHit(currentHit.value - 1);
    }
    function onQuery(value) {
      query.value = value;
    }
    const copied = ref(false);
    let copiedTimer;
    async function copyLog() {
      if (!navigator.clipboard) return;
      try {
        await navigator.clipboard.writeText(store.logText);
        copied.value = true;
        if (copiedTimer) clearTimeout(copiedTimer);
        copiedTimer = setTimeout(() => copied.value = false, 1200);
      } catch {
      }
    }
    watch(
      [open, tab, () => route.params.taskId],
      ([isOpen, whichTab, id]) => {
        if (isOpen && whichTab === "log" && typeof id === "string" && id) store.startLog(id);
        else store.stopLog();
      },
      { immediate: true }
    );
    onBeforeUnmount(() => {
      store.stopLog();
      if (copiedTimer) clearTimeout(copiedTimer);
    });
    let lastFocused = null;
    watch(open, (isOpen) => {
      if (isOpen) {
        lastFocused = document.activeElement ?? null;
      } else {
        const target = lastFocused;
        lastFocused = null;
        void nextTick(() => target?.focus?.());
      }
    });
    watch(
      () => route.params.taskId,
      (id) => {
        if (typeof id === "string" && id) void store.openTask(id);
        else store.closeTask();
      },
      { immediate: true }
    );
    const mountAttempt = ref(0);
    function drawerIsInDocument() {
      return document.querySelector(".tp-drawer") !== null;
    }
    watch([open, mountAttempt], async () => {
      if (!open.value) {
        mountAttempt.value = 0;
        return;
      }
      await nextTick();
      if (shouldRetryDrawerMount({
        open: open.value,
        mounted: drawerIsInDocument(),
        attempt: mountAttempt.value
      })) {
        mountAttempt.value += 1;
      }
    });
    return (_ctx, _cache) => {
      const _component_el_drawer = resolveComponent("el-drawer");
      return openBlock(), createBlock(_component_el_drawer, {
        key: unref(drawerMountKey)(mountAttempt.value),
        "model-value": open.value,
        size: 520,
        direction: "rtl",
        "with-header": false,
        class: "tp-drawer",
        "onUpdate:modelValue": onVisible
      }, {
        default: withCtx(() => [
          task.value ? (openBlock(), createElementBlock(Fragment, { key: 0 }, [
            createBaseVNode("div", _hoisted_1, [
              createBaseVNode("span", {
                class: "sc",
                "data-status": task.value.status
              }, [
                createVNode(StatusMark, {
                  status: task.value.status,
                  shape: "dot"
                }, null, 8, ["status"]),
                createTextVNode(" " + toDisplayString(unref(t)(`status.${task.value.status}`)), 1)
              ], 8, _hoisted_2),
              createBaseVNode("span", _hoisted_3, toDisplayString(task.value.id), 1),
              createBaseVNode("span", _hoisted_4, [
                createTextVNode(toDisplayString(dur.value), 1),
                _cache[8] || (_cache[8] = createBaseVNode("br", null, null, -1)),
                createTextVNode(toDisplayString(started.value) + " → " + toDisplayString(ended.value), 1)
              ]),
              createBaseVNode("button", {
                class: "x",
                type: "button",
                "aria-label": unref(t)("drawer.close"),
                onClick: close
              }, "✕", 8, _hoisted_5)
            ]),
            createBaseVNode("div", _hoisted_6, [
              createBaseVNode("button", {
                role: "tab",
                type: "button",
                "aria-selected": tab.value === "overview",
                class: normalizeClass({ on: tab.value === "overview" }),
                onClick: _cache[0] || (_cache[0] = ($event) => go("overview")),
                onKeydown: [
                  _cache[1] || (_cache[1] = withKeys(withModifiers(($event) => go("overview"), ["prevent"]), ["enter"])),
                  _cache[2] || (_cache[2] = withKeys(withModifiers(($event) => go("overview"), ["prevent"]), ["space"]))
                ]
              }, toDisplayString(unref(t)("drawer.tab.overview")), 43, _hoisted_7),
              createBaseVNode("button", {
                role: "tab",
                type: "button",
                "aria-selected": tab.value === "log",
                class: normalizeClass({ on: tab.value === "log" }),
                onClick: _cache[3] || (_cache[3] = ($event) => go("log")),
                onKeydown: [
                  _cache[4] || (_cache[4] = withKeys(withModifiers(($event) => go("log"), ["prevent"]), ["enter"])),
                  _cache[5] || (_cache[5] = withKeys(withModifiers(($event) => go("log"), ["prevent"]), ["space"]))
                ]
              }, toDisplayString(unref(t)("drawer.tab.log")), 43, _hoisted_8)
            ]),
            withDirectives(createBaseVNode("div", _hoisted_9, [
              createBaseVNode("section", _hoisted_10, [
                createBaseVNode("h4", null, toDisplayString(unref(t)("drawer.brief")), 1),
                createBaseVNode("pre", _hoisted_11, toDisplayString(task.value.brief), 1)
              ]),
              createBaseVNode("section", _hoisted_12, [
                createBaseVNode("h4", null, [
                  createTextVNode(toDisplayString(unref(t)("drawer.timeline")) + " ", 1),
                  createBaseVNode("span", {
                    class: "live",
                    "data-off": unref(store).polling ? null : ""
                  }, [
                    _cache[9] || (_cache[9] = createBaseVNode("i", null, null, -1)),
                    createTextVNode(toDisplayString(unref(store).polling ? unref(t)("live.on") : unref(t)("live.off")), 1)
                  ], 8, _hoisted_13)
                ]),
                createBaseVNode("ol", _hoisted_14, [
                  (openBlock(true), createElementBlock(Fragment, null, renderList(timeline.value, (entry, index) => {
                    return openBlock(), createElementBlock("li", {
                      key: index,
                      class: normalizeClass(["ev", { now: liveTask.value && index === timeline.value.length - 1, isbad: entry.bad }])
                    }, [
                      _cache[10] || (_cache[10] = createBaseVNode("span", { class: "dot" }, null, -1)),
                      createBaseVNode("span", _hoisted_15, toDisplayString(entry.t), 1),
                      createBaseVNode("span", _hoisted_16, toDisplayString(entry.k), 1),
                      createBaseVNode("span", _hoisted_17, toDisplayString(entry.g), 1),
                      entry.d ? (openBlock(), createElementBlock("span", _hoisted_18, toDisplayString(entry.d), 1)) : createCommentVNode("", true)
                    ], 2);
                  }), 128)),
                  !timeline.value.length ? (openBlock(), createElementBlock("li", _hoisted_19, [..._cache[11] || (_cache[11] = [
                    createBaseVNode("span", { class: "dot" }, null, -1),
                    createBaseVNode("span", { class: "t" }, "—", -1)
                  ])])) : createCommentVNode("", true)
                ])
              ]),
              verify.value != null ? (openBlock(), createElementBlock("section", _hoisted_20, [
                createBaseVNode("h4", null, [
                  createTextVNode(toDisplayString(unref(t)("drawer.verdict")), 1),
                  createBaseVNode("em", null, "— " + toDisplayString(unref(t)("verdict.by")), 1)
                ]),
                createBaseVNode("div", _hoisted_21, [
                  createBaseVNode("span", {
                    class: normalizeClass(["vdot", { bad: verify.value !== 0 }])
                  }, null, 2),
                  createBaseVNode("span", _hoisted_22, toDisplayString(unref(t)(verify.value === 0 ? "verdict.passed" : "verdict.failed")), 1),
                  createBaseVNode("span", {
                    class: normalizeClass(["vcode", { bad: verify.value !== 0 }])
                  }, "exit " + toDisplayString(verify.value), 3)
                ]),
                task.value.verify_cmd ? (openBlock(), createElementBlock("p", _hoisted_23, toDisplayString(task.value.verify_cmd), 1)) : createCommentVNode("", true)
              ])) : createCommentVNode("", true),
              createBaseVNode("div", {
                class: normalizeClass(["duel", { solo: !showClaim.value }])
              }, [
                showClaim.value ? (openBlock(), createElementBlock("div", _hoisted_24, [
                  createBaseVNode("h5", null, toDisplayString(unref(t)("drawer.claim")), 1),
                  createBaseVNode("p", _hoisted_25, toDisplayString(task.value.reasoning || unref(t)("drawer.noClaim")), 1)
                ])) : createCommentVNode("", true),
                showClaim.value ? (openBlock(), createElementBlock("div", _hoisted_26)) : createCommentVNode("", true),
                createBaseVNode("div", _hoisted_27, [
                  createBaseVNode("h5", null, toDisplayString(unref(t)("drawer.evidence")), 1),
                  createBaseVNode("dl", null, [
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.exit")), 1),
                    createBaseVNode("dd", null, toDisplayString(task.value.exit_code ?? "—"), 1),
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.verify")), 1),
                    createBaseVNode("dd", {
                      class: normalizeClass({ bad: verify.value != null && verify.value !== 0, good: verify.value === 0 })
                    }, toDisplayString(verifyText.value), 3),
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.files")), 1),
                    createBaseVNode("dd", null, toDisplayString(task.value.files_changed_live ?? task.value.files_changed ?? 0), 1),
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.adapter")), 1),
                    createBaseVNode("dd", null, toDisplayString(task.value.adapter ?? "—") + toDisplayString(task.value.model ? ` · ${task.value.model}` : ""), 1),
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.group")), 1),
                    createBaseVNode("dd", null, toDisplayString(task.value.group_name ?? "—"), 1),
                    createBaseVNode("dt", null, toDisplayString(unref(t)("ev.lane")), 1),
                    createBaseVNode("dd", null, toDisplayString(task.value.project), 1)
                  ])
                ])
              ], 2)
            ], 512), [
              [vShow, tab.value === "overview"]
            ]),
            withDirectives(createBaseVNode("div", _hoisted_28, [
              createBaseVNode("div", _hoisted_29, [
                createBaseVNode("input", {
                  class: "logq",
                  type: "search",
                  value: query.value,
                  placeholder: unref(t)("log.search.placeholder"),
                  "aria-label": unref(t)("log.search.placeholder"),
                  onInput: _cache[6] || (_cache[6] = ($event) => onQuery($event.target.value))
                }, null, 40, _hoisted_30),
                createBaseVNode("span", _hoisted_31, toDisplayString(hitPosition.value) + " / " + toDisplayString(matchCount.value), 1),
                createBaseVNode("button", {
                  type: "button",
                  class: "lognav",
                  "aria-label": unref(t)("log.search.prev"),
                  disabled: !matchCount.value,
                  onClick: prevHit
                }, " ↑ ", 8, _hoisted_32),
                createBaseVNode("button", {
                  type: "button",
                  class: "lognav",
                  "aria-label": unref(t)("log.search.next"),
                  disabled: !matchCount.value,
                  onClick: nextHit
                }, " ↓ ", 8, _hoisted_33),
                createBaseVNode("button", {
                  type: "button",
                  class: "logact",
                  onClick: copyLog
                }, toDisplayString(copied.value ? unref(t)("log.copied") : unref(t)("log.copy")), 1),
                createBaseVNode("button", {
                  type: "button",
                  class: "logact",
                  onClick: _cache[7] || (_cache[7] = ($event) => unref(store).refreshLog())
                }, toDisplayString(unref(t)("log.refresh")), 1)
              ]),
              createBaseVNode("p", _hoisted_34, [
                createTextVNode(toDisplayString(unref(t)("log.search.scope", { n: unref(formatBytes)(unref(byteLength)(unref(store).logText)) })) + " ", 1),
                query.value && !matchCount.value ? (openBlock(), createElementBlock("span", _hoisted_35, toDisplayString(unref(t)("log.search.none")), 1)) : createCommentVNode("", true)
              ]),
              unref(store).logOmitted > 0 ? (openBlock(), createElementBlock("p", _hoisted_36, toDisplayString(unref(t)("log.omitted", { n: unref(formatBytes)(unref(store).logOmitted) })), 1)) : createCommentVNode("", true),
              unref(store).logTruncated ? (openBlock(), createElementBlock("p", _hoisted_37, toDisplayString(unref(t)("log.truncated", { n: unref(LOG_MAX_LINES) })), 1)) : createCommentVNode("", true),
              unref(store).logError ? (openBlock(), createElementBlock("p", _hoisted_38, toDisplayString(unref(store).logError), 1)) : createCommentVNode("", true),
              createBaseVNode("div", {
                ref_key: "logEl",
                ref: logEl,
                class: "logscroll",
                onScroll: onLogScroll
              }, [
                !logLines.value.length && !unref(store).logError ? (openBlock(), createElementBlock("p", _hoisted_39, toDisplayString(unref(t)("log.empty")), 1)) : createCommentVNode("", true),
                (openBlock(true), createElementBlock(Fragment, null, renderList(logLines.value, (line, index) => {
                  return openBlock(), createElementBlock("div", {
                    key: index,
                    class: normalizeClass(["logline", { cur: isCurrentHitLine(index) }]),
                    "data-line": index
                  }, [
                    (openBlock(true), createElementBlock(Fragment, null, renderList(unref(highlightSegments)(line, query.value), (seg, si) => {
                      return openBlock(), createElementBlock("span", {
                        key: si,
                        class: normalizeClass({ hit: seg.hit })
                      }, toDisplayString(seg.text), 3);
                    }), 128))
                  ], 10, _hoisted_40);
                }), 128))
              ], 544),
              !stuck.value ? (openBlock(), createElementBlock("button", {
                key: 3,
                type: "button",
                class: "logjump",
                onClick: jumpBottom
              }, toDisplayString(unref(t)("log.jumpBottom", { n: newLines.value })), 1)) : createCommentVNode("", true)
            ], 512), [
              [vShow, tab.value === "log"]
            ])
          ], 64)) : (openBlock(), createElementBlock("p", _hoisted_41, toDisplayString(unref(t)("drawer.noTask")), 1))
        ]),
        _: 1
      }, 8, ["model-value"]);
    };
  }
});
const TaskDrawer = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-10de8666"]]);
export {
  StatusMark as S,
  TaskDrawer as T,
  duration as d
};
