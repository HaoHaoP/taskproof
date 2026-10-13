import { d as defineComponent, i as useBoardStore, j as useSettingsStore, u as useI18n, k as watch, a8 as onMounted, c as createElementBlock, b as createBaseVNode, t as toDisplayString, f as unref, g as createCommentVNode, e as createVNode, l as withCtx, a9 as openAbout, F as Fragment, r as renderList, aa as STATUS_IDS, ab as VERIFY_KINDS, ac as hasDesktopHost, h as computed, U as ref, p as resolveComponent, y as createTextVNode, n as normalizeClass, o as openBlock, _ as _export_sfc } from "./index-B-PLdDbR.js";
const _hoisted_1 = { class: "settings-view" };
const _hoisted_2 = { class: "panes grouped" };
const _hoisted_3 = { class: "setwrap" };
const _hoisted_4 = { class: "sub" };
const _hoisted_5 = {
  key: 0,
  class: "sub browser-note"
};
const _hoisted_6 = { class: "setgroup" };
const _hoisted_7 = { class: "setcard" };
const _hoisted_8 = { class: "setrow" };
const _hoisted_9 = { class: "lab" };
const _hoisted_10 = { class: "t" };
const _hoisted_11 = { class: "ctl" };
const _hoisted_12 = { class: "setrow" };
const _hoisted_13 = { class: "lab" };
const _hoisted_14 = { class: "t" };
const _hoisted_15 = { class: "d" };
const _hoisted_16 = { class: "ctl" };
const _hoisted_17 = { class: "setrow" };
const _hoisted_18 = { class: "lab" };
const _hoisted_19 = { class: "t" };
const _hoisted_20 = { class: "d" };
const _hoisted_21 = { class: "ctl" };
const _hoisted_22 = {
  key: 1,
  class: "setgroup"
};
const _hoisted_23 = { class: "setcard" };
const _hoisted_24 = { class: "setrow" };
const _hoisted_25 = { class: "lab" };
const _hoisted_26 = { class: "t" };
const _hoisted_27 = { class: "d" };
const _hoisted_28 = { class: "ctl" };
const _hoisted_29 = {
  key: 0,
  class: "setrow"
};
const _hoisted_30 = { class: "lab" };
const _hoisted_31 = { class: "t" };
const _hoisted_32 = { class: "d" };
const _hoisted_33 = { class: "ctl" };
const _hoisted_34 = { class: "setrow" };
const _hoisted_35 = { class: "lab" };
const _hoisted_36 = { class: "t" };
const _hoisted_37 = { class: "d" };
const _hoisted_38 = { class: "ctl wide" };
const _hoisted_39 = { class: "setrow" };
const _hoisted_40 = { class: "lab" };
const _hoisted_41 = { class: "t" };
const _hoisted_42 = { class: "d" };
const _hoisted_43 = { class: "ctl" };
const _hoisted_44 = { class: "ro" };
const _hoisted_45 = { class: "setrow" };
const _hoisted_46 = { class: "lab" };
const _hoisted_47 = { class: "t" };
const _hoisted_48 = { class: "ctl" };
const _hoisted_49 = {
  key: 2,
  class: "setgroup"
};
const _hoisted_50 = { class: "setcard" };
const _hoisted_51 = { class: "setrow" };
const _hoisted_52 = { class: "lab" };
const _hoisted_53 = { class: "t" };
const _hoisted_54 = { class: "d" };
const _hoisted_55 = { class: "ctl" };
const _hoisted_56 = { class: "ro" };
const _hoisted_57 = { class: "setrow" };
const _hoisted_58 = { class: "lab" };
const _hoisted_59 = { class: "t" };
const _hoisted_60 = { class: "d" };
const _hoisted_61 = { class: "ctl wide" };
const _hoisted_62 = { class: "ro argvcopy" };
const _hoisted_63 = {
  key: 0,
  class: "setrow"
};
const _hoisted_64 = { class: "lab" };
const _hoisted_65 = { class: "t" };
const _hoisted_66 = { class: "d gitmissing" };
const _hoisted_67 = {
  key: 3,
  class: "setgroup"
};
const _hoisted_68 = { class: "setcard" };
const _hoisted_69 = { class: "setrow" };
const _hoisted_70 = { class: "lab" };
const _hoisted_71 = { class: "t" };
const _hoisted_72 = { class: "ctl" };
const _hoisted_73 = { class: "setrow" };
const _hoisted_74 = { class: "lab" };
const _hoisted_75 = { class: "t" };
const _hoisted_76 = { class: "ctl" };
const _hoisted_77 = { class: "setrow" };
const _hoisted_78 = { class: "lab" };
const _hoisted_79 = { class: "t" };
const _hoisted_80 = { class: "ctl" };
const _hoisted_81 = { class: "setrow" };
const _hoisted_82 = { class: "lab" };
const _hoisted_83 = { class: "t" };
const _hoisted_84 = { class: "d" };
const _hoisted_85 = { class: "ctl" };
const _hoisted_86 = { class: "setrow" };
const _hoisted_87 = { class: "lab" };
const _hoisted_88 = { class: "t" };
const _hoisted_89 = { class: "d" };
const _hoisted_90 = { class: "ctl" };
const _hoisted_91 = { class: "setgroup" };
const _hoisted_92 = { class: "setcard" };
const _hoisted_93 = { class: "setrow" };
const _hoisted_94 = { class: "lab" };
const _hoisted_95 = { class: "t" };
const _hoisted_96 = { class: "d" };
const _hoisted_97 = { class: "ctl" };
const _hoisted_98 = { class: "setrow" };
const _hoisted_99 = { class: "lab" };
const _hoisted_100 = { class: "t" };
const _hoisted_101 = { class: "ctl" };
const _hoisted_102 = { class: "ro" };
const _hoisted_103 = { class: "setrow" };
const _hoisted_104 = { class: "lab" };
const _hoisted_105 = { class: "t" };
const _hoisted_106 = { class: "d" };
const _hoisted_107 = { class: "ctl" };
const _hoisted_108 = {
  key: 0,
  class: "alamps"
};
const _hoisted_109 = ["title"];
const _hoisted_110 = {
  key: 1,
  class: "ro"
};
const _hoisted_111 = { class: "setrow" };
const _hoisted_112 = { class: "lab" };
const _hoisted_113 = { class: "t" };
const _hoisted_114 = { class: "d" };
const _hoisted_115 = { class: "ctl" };
const _hoisted_116 = { class: "ro" };
const _hoisted_117 = { class: "setrow" };
const _hoisted_118 = { class: "lab" };
const _hoisted_119 = { class: "t" };
const _hoisted_120 = { class: "d" };
const _hoisted_121 = { class: "ctl" };
const _hoisted_122 = { class: "ro" };
const _hoisted_123 = { class: "setrow" };
const _hoisted_124 = { class: "lab" };
const _hoisted_125 = { class: "t" };
const _hoisted_126 = { class: "d" };
const _hoisted_127 = { class: "ctl" };
const _sfc_main = /* @__PURE__ */ defineComponent({
  __name: "SettingsView",
  setup(__props) {
    const board = useBoardStore();
    const settings = useSettingsStore();
    const { t } = useI18n();
    const hasHost = hasDesktopHost();
    const contractLine = computed(
      () => board.unknownWords.length ? t("settings.contractDrift") : t("settings.contractSynced")
    );
    const workspaceLabel = computed(() => {
      const path = settings.settings.workspace ?? "";
      const short = path.replace(/^\/Users\/[^/]+/, "~");
      return short || "~/.taskproof";
    });
    const registryPath = computed(() => {
      const ws = (settings.settings.workspace || "~/.taskproof").replace(/\/+$/, "");
      return `${ws}/projects.toml`;
    });
    const cap = ref(null);
    const capLine = computed(() => {
      const setting = cap.value;
      if (!setting || typeof setting.value !== "number") return "—";
      const gloss = setting.source === "auto" ? t("settings.capAuto", { detail: setting.detail }) : setting.source === "cli" ? t("settings.capCli", { detail: setting.detail }) : setting.detail;
      return `${t("settings.capLabel")} ${setting.value}（${gloss}）`;
    });
    async function loadCap() {
      const port = board.service.port;
      if (!port) return;
      try {
        const response = await fetch(`http://127.0.0.1:${port}/api/health`, {
          headers: { accept: "application/json" }
        });
        if (!response.ok) return;
        const body = await response.json();
        if (body.concurrency && typeof body.concurrency.value === "number") {
          cap.value = body.concurrency;
        }
      } catch {
      }
    }
    watch(
      () => board.service.port,
      (port) => {
        if (port) void loadCap();
      },
      { immediate: true }
    );
    const languageOptions = computed(() => [
      { label: t("lang.system"), value: "system" },
      { label: "中文", value: "zh-CN" },
      { label: "EN", value: "en" }
    ]);
    const themeOptions = computed(() => [
      { label: t("theme.dark"), value: "dark" },
      { label: t("theme.light"), value: "light" },
      { label: t("theme.system"), value: "system" }
    ]);
    const pollOptions = computed(() => [
      { label: t("settings.pollOn"), value: "2s" },
      { label: t("settings.pollOff"), value: "off" }
    ]);
    const portModeOptions = computed(() => [
      { label: t("settings.portmodeAuto"), value: "auto" },
      { label: t("settings.portmodeFixed"), value: "fixed" }
    ]);
    const launchOptions = computed(() => [
      { label: t("settings.launchAuto"), value: "auto" },
      { label: t("settings.launchManual"), value: "manual" }
    ]);
    const adapters = ref(null);
    const diagnostics = ref(null);
    async function loadDiagnostics() {
      const tp = window.tp;
      if (!tp) return;
      diagnostics.value = await tp.app.diagnostics();
    }
    onMounted(async () => {
      const tp = window.tp;
      if (!tp) return;
      adapters.value = await tp.app.adapters();
      await loadDiagnostics();
    });
    watch(
      () => settings.settings.taskproofPath,
      () => {
        void loadDiagnostics();
      }
    );
    const launchSourceLabel = computed(() => {
      const source = diagnostics.value?.launch.source;
      return source ? t(`settings.source.${source}`) : "—";
    });
    const launchArgv = computed(() => diagnostics.value?.launch.argv.join(" ") ?? "");
    const gitMissing = computed(() => diagnostics.value?.gitAvailable === false);
    function onLanguage(value) {
      settings.setLanguage(value);
    }
    function onTheme(value) {
      settings.setTheme(value);
    }
    function onPoll(value) {
      settings.setPoll(value);
    }
    function onPortMode(value) {
      settings.setPortMode(value);
    }
    function onLaunch(value) {
      settings.setLaunch(value);
    }
    function onPort(value) {
      const port = Number(value);
      if (Number.isFinite(port) && port > 0) settings.setPort(port);
    }
    function onTaskproofPath(value) {
      settings.setTaskproofPath(String(value));
    }
    function openRegistry() {
      void window.tp?.shell.openPath(registryPath.value);
    }
    return (_ctx, _cache) => {
      const _component_el_segmented = resolveComponent("el-segmented");
      const _component_el_input = resolveComponent("el-input");
      const _component_el_switch = resolveComponent("el-switch");
      const _component_el_button = resolveComponent("el-button");
      return openBlock(), createElementBlock("div", _hoisted_1, [
        createBaseVNode("div", _hoisted_2, [
          createBaseVNode("div", _hoisted_3, [
            createBaseVNode("h3", null, toDisplayString(unref(t)("settings.title")), 1),
            createBaseVNode("p", _hoisted_4, toDisplayString(unref(t)("settings.sub")), 1),
            !unref(hasHost) ? (openBlock(), createElementBlock("p", _hoisted_5, toDisplayString(unref(t)("settings.browserNote")), 1)) : createCommentVNode("", true),
            createBaseVNode("section", _hoisted_6, [
              createBaseVNode("h4", null, toDisplayString(unref(t)("settings.appearance")), 1),
              createBaseVNode("div", _hoisted_7, [
                createBaseVNode("div", _hoisted_8, [
                  createBaseVNode("div", _hoisted_9, [
                    createBaseVNode("div", _hoisted_10, toDisplayString(unref(t)("settings.language")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_11, [
                    createVNode(_component_el_segmented, {
                      "model-value": unref(settings).settings.language,
                      size: "small",
                      options: languageOptions.value,
                      "onUpdate:modelValue": onLanguage
                    }, null, 8, ["model-value", "options"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_12, [
                  createBaseVNode("div", _hoisted_13, [
                    createBaseVNode("div", _hoisted_14, toDisplayString(unref(t)("settings.theme")), 1),
                    createBaseVNode("div", _hoisted_15, toDisplayString(unref(t)("settings.themeDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_16, [
                    createVNode(_component_el_segmented, {
                      "model-value": unref(settings).settings.theme,
                      size: "small",
                      options: themeOptions.value,
                      "onUpdate:modelValue": onTheme
                    }, null, 8, ["model-value", "options"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_17, [
                  createBaseVNode("div", _hoisted_18, [
                    createBaseVNode("div", _hoisted_19, toDisplayString(unref(t)("settings.poll")), 1),
                    createBaseVNode("div", _hoisted_20, toDisplayString(unref(t)("settings.pollDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_21, [
                    createVNode(_component_el_segmented, {
                      "model-value": unref(settings).settings.poll,
                      size: "small",
                      options: pollOptions.value,
                      "onUpdate:modelValue": onPoll
                    }, null, 8, ["model-value", "options"])
                  ])
                ])
              ])
            ]),
            unref(hasHost) ? (openBlock(), createElementBlock("section", _hoisted_22, [
              createBaseVNode("h4", null, toDisplayString(unref(t)("settings.service")), 1),
              createBaseVNode("div", _hoisted_23, [
                createBaseVNode("div", _hoisted_24, [
                  createBaseVNode("div", _hoisted_25, [
                    createBaseVNode("div", _hoisted_26, toDisplayString(unref(t)("settings.portmode")), 1),
                    createBaseVNode("div", _hoisted_27, toDisplayString(unref(t)("settings.portmodeDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_28, [
                    createVNode(_component_el_segmented, {
                      "model-value": unref(settings).settings.portMode,
                      size: "small",
                      options: portModeOptions.value,
                      "onUpdate:modelValue": onPortMode
                    }, null, 8, ["model-value", "options"])
                  ])
                ]),
                unref(settings).settings.portMode === "fixed" ? (openBlock(), createElementBlock("div", _hoisted_29, [
                  createBaseVNode("div", _hoisted_30, [
                    createBaseVNode("div", _hoisted_31, toDisplayString(unref(t)("settings.port")), 1),
                    createBaseVNode("div", _hoisted_32, toDisplayString(unref(t)("settings.portDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_33, [
                    createVNode(_component_el_input, {
                      "model-value": String(unref(settings).settings.port),
                      type: "number",
                      size: "small",
                      style: { "width": "110px" },
                      "onUpdate:modelValue": onPort
                    }, null, 8, ["model-value"])
                  ])
                ])) : createCommentVNode("", true),
                createBaseVNode("div", _hoisted_34, [
                  createBaseVNode("div", _hoisted_35, [
                    createBaseVNode("div", _hoisted_36, toDisplayString(unref(t)("settings.taskproof")), 1),
                    createBaseVNode("div", _hoisted_37, toDisplayString(unref(t)("settings.taskproofDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_38, [
                    createVNode(_component_el_input, {
                      "model-value": unref(settings).settings.taskproofPath,
                      size: "small",
                      placeholder: "/opt/homebrew/bin/taskproof",
                      "onUpdate:modelValue": onTaskproofPath
                    }, null, 8, ["model-value"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_39, [
                  createBaseVNode("div", _hoisted_40, [
                    createBaseVNode("div", _hoisted_41, toDisplayString(unref(t)("settings.workspace")), 1),
                    createBaseVNode("div", _hoisted_42, toDisplayString(unref(t)("settings.workspaceDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_43, [
                    createBaseVNode("span", _hoisted_44, toDisplayString(workspaceLabel.value), 1)
                  ])
                ]),
                createBaseVNode("div", _hoisted_45, [
                  createBaseVNode("div", _hoisted_46, [
                    createBaseVNode("div", _hoisted_47, toDisplayString(unref(t)("settings.launch")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_48, [
                    createVNode(_component_el_segmented, {
                      "model-value": unref(settings).settings.launch,
                      size: "small",
                      options: launchOptions.value,
                      "onUpdate:modelValue": onLaunch
                    }, null, 8, ["model-value", "options"])
                  ])
                ])
              ])
            ])) : createCommentVNode("", true),
            unref(hasHost) ? (openBlock(), createElementBlock("section", _hoisted_49, [
              createBaseVNode("h4", null, toDisplayString(unref(t)("settings.diagnostics")), 1),
              createBaseVNode("div", _hoisted_50, [
                createBaseVNode("div", _hoisted_51, [
                  createBaseVNode("div", _hoisted_52, [
                    createBaseVNode("div", _hoisted_53, toDisplayString(unref(t)("settings.launchSource")), 1),
                    createBaseVNode("div", _hoisted_54, toDisplayString(unref(t)("settings.launchSourceDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_55, [
                    createBaseVNode("span", _hoisted_56, toDisplayString(launchSourceLabel.value), 1)
                  ])
                ]),
                createBaseVNode("div", _hoisted_57, [
                  createBaseVNode("div", _hoisted_58, [
                    createBaseVNode("div", _hoisted_59, toDisplayString(unref(t)("settings.launchArgv")), 1),
                    createBaseVNode("div", _hoisted_60, toDisplayString(unref(t)("settings.launchArgvDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_61, [
                    createBaseVNode("span", _hoisted_62, toDisplayString(launchArgv.value || "—"), 1)
                  ])
                ]),
                gitMissing.value ? (openBlock(), createElementBlock("div", _hoisted_63, [
                  createBaseVNode("div", _hoisted_64, [
                    createBaseVNode("div", _hoisted_65, toDisplayString(unref(t)("settings.git")), 1),
                    createBaseVNode("div", _hoisted_66, toDisplayString(unref(t)("settings.gitMissing")), 1)
                  ])
                ])) : createCommentVNode("", true)
              ])
            ])) : createCommentVNode("", true),
            unref(hasHost) ? (openBlock(), createElementBlock("section", _hoisted_67, [
              createBaseVNode("h4", null, toDisplayString(unref(t)("settings.desktop")), 1),
              createBaseVNode("div", _hoisted_68, [
                createBaseVNode("div", _hoisted_69, [
                  createBaseVNode("div", _hoisted_70, [
                    createBaseVNode("div", _hoisted_71, toDisplayString(unref(t)("settings.notifyFail")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_72, [
                    createVNode(_component_el_switch, {
                      "model-value": unref(settings).settings.notifyFail,
                      onChange: _cache[0] || (_cache[0] = ($event) => unref(settings).setFlag("notifyFail", $event))
                    }, null, 8, ["model-value"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_73, [
                  createBaseVNode("div", _hoisted_74, [
                    createBaseVNode("div", _hoisted_75, toDisplayString(unref(t)("settings.notifyDone")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_76, [
                    createVNode(_component_el_switch, {
                      "model-value": unref(settings).settings.notifyDone,
                      onChange: _cache[1] || (_cache[1] = ($event) => unref(settings).setFlag("notifyDone", $event))
                    }, null, 8, ["model-value"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_77, [
                  createBaseVNode("div", _hoisted_78, [
                    createBaseVNode("div", _hoisted_79, toDisplayString(unref(t)("settings.dockBadge")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_80, [
                    createVNode(_component_el_switch, {
                      "model-value": unref(settings).settings.dockBadge,
                      onChange: _cache[2] || (_cache[2] = ($event) => unref(settings).setFlag("dockBadge", $event))
                    }, null, 8, ["model-value"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_81, [
                  createBaseVNode("div", _hoisted_82, [
                    createBaseVNode("div", _hoisted_83, toDisplayString(unref(t)("settings.tray")), 1),
                    createBaseVNode("div", _hoisted_84, toDisplayString(unref(t)("settings.trayDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_85, [
                    createVNode(_component_el_switch, {
                      "model-value": unref(settings).settings.tray,
                      onChange: _cache[3] || (_cache[3] = ($event) => unref(settings).setFlag("tray", $event))
                    }, null, 8, ["model-value"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_86, [
                  createBaseVNode("div", _hoisted_87, [
                    createBaseVNode("div", _hoisted_88, toDisplayString(unref(t)("settings.autostart")), 1),
                    createBaseVNode("div", _hoisted_89, toDisplayString(unref(t)("settings.autostartDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_90, [
                    createVNode(_component_el_switch, {
                      "model-value": unref(settings).settings.autostart,
                      onChange: _cache[4] || (_cache[4] = ($event) => unref(settings).setFlag("autostart", $event))
                    }, null, 8, ["model-value"])
                  ])
                ])
              ])
            ])) : createCommentVNode("", true),
            createBaseVNode("section", _hoisted_91, [
              createBaseVNode("h4", null, toDisplayString(unref(t)("settings.about")), 1),
              createBaseVNode("div", _hoisted_92, [
                createBaseVNode("div", _hoisted_93, [
                  createBaseVNode("div", _hoisted_94, [
                    createBaseVNode("div", _hoisted_95, toDisplayString(unref(t)("settings.aboutTaskproof")), 1),
                    createBaseVNode("div", _hoisted_96, toDisplayString(unref(t)("settings.aboutTaskproofDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_97, [
                    createVNode(_component_el_button, {
                      size: "small",
                      onClick: unref(openAbout)
                    }, {
                      default: withCtx(() => [
                        createTextVNode(toDisplayString(unref(t)("about.open")), 1)
                      ]),
                      _: 1
                    }, 8, ["onClick"])
                  ])
                ]),
                createBaseVNode("div", _hoisted_98, [
                  createBaseVNode("div", _hoisted_99, [
                    createBaseVNode("div", _hoisted_100, toDisplayString(unref(t)("settings.version")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_101, [
                    createBaseVNode("span", _hoisted_102, toDisplayString(unref(settings).version || unref(board).version || "0.1.0"), 1)
                  ])
                ]),
                createBaseVNode("div", _hoisted_103, [
                  createBaseVNode("div", _hoisted_104, [
                    createBaseVNode("div", _hoisted_105, toDisplayString(unref(t)("settings.adapters")), 1),
                    createBaseVNode("div", _hoisted_106, toDisplayString(unref(t)("settings.adaptersDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_107, [
                    adapters.value && adapters.value.length ? (openBlock(), createElementBlock("div", _hoisted_108, [
                      (openBlock(true), createElementBlock(Fragment, null, renderList(adapters.value, (a) => {
                        return openBlock(), createElementBlock("span", {
                          key: a.name,
                          class: normalizeClass(["alamp", { bad: !a.installed }]),
                          title: a.detail
                        }, [
                          _cache[5] || (_cache[5] = createBaseVNode("i", null, null, -1)),
                          createTextVNode(toDisplayString(a.name), 1)
                        ], 10, _hoisted_109);
                      }), 128))
                    ])) : (openBlock(), createElementBlock("span", _hoisted_110, "—"))
                  ])
                ]),
                createBaseVNode("div", _hoisted_111, [
                  createBaseVNode("div", _hoisted_112, [
                    createBaseVNode("div", _hoisted_113, toDisplayString(unref(t)("settings.contract")), 1),
                    createBaseVNode("div", _hoisted_114, toDisplayString(contractLine.value), 1)
                  ]),
                  createBaseVNode("div", _hoisted_115, [
                    createBaseVNode("span", _hoisted_116, toDisplayString(unref(STATUS_IDS).length) + " " + toDisplayString(unref(t)("status.label")) + " · " + toDisplayString(unref(VERIFY_KINDS).join(" / ")), 1)
                  ])
                ]),
                createBaseVNode("div", _hoisted_117, [
                  createBaseVNode("div", _hoisted_118, [
                    createBaseVNode("div", _hoisted_119, toDisplayString(unref(t)("settings.limits")), 1),
                    createBaseVNode("div", _hoisted_120, toDisplayString(unref(t)("settings.limitsDesc")), 1)
                  ]),
                  createBaseVNode("div", _hoisted_121, [
                    createBaseVNode("span", _hoisted_122, toDisplayString(capLine.value), 1)
                  ])
                ]),
                createBaseVNode("div", _hoisted_123, [
                  createBaseVNode("div", _hoisted_124, [
                    createBaseVNode("div", _hoisted_125, toDisplayString(unref(t)("settings.registry")), 1),
                    createBaseVNode("div", _hoisted_126, toDisplayString(registryPath.value), 1)
                  ]),
                  createBaseVNode("div", _hoisted_127, [
                    createVNode(_component_el_button, {
                      size: "small",
                      onClick: openRegistry
                    }, {
                      default: withCtx(() => [
                        createTextVNode(toDisplayString(unref(t)("settings.openRegistry")), 1)
                      ]),
                      _: 1
                    })
                  ])
                ])
              ])
            ])
          ])
        ])
      ]);
    };
  }
});
const SettingsView = /* @__PURE__ */ _export_sfc(_sfc_main, [["__scopeId", "data-v-9b13aa18"]]);
export {
  SettingsView as default
};
