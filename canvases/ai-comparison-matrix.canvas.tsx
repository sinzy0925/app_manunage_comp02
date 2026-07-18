import {
  BarChart,
  Callout,
  Card,
  CardBody,
  CardHeader,
  Divider,
  Grid,
  H1,
  H2,
  H3,
  Pill,
  Row,
  Spacer,
  Stack,
  Stat,
  Table,
  Text,
  useHostTheme,
} from "cursor/canvas";

type Cell = {
  quality: number;
  time: string;
  timeSec: number;
  cost: string;
  costUsd: number;
  note: string;
};

const DATA: Record<string, Record<string, Cell>> = {
  marunage: {
    composer: {
      quality: 6,
      time: "1分18秒",
      timeSec: 78,
      cost: "$0.29",
      costUsd: 0.29,
      note: "速いが幻覚リスク",
    },
    claude: {
      quality: 7,
      time: "4分59秒",
      timeSec: 299,
      cost: "$1.43",
      costUsd: 1.43,
      note: "最長・高コスト帯",
    },
  },
  skill: {
    composer: {
      quality: 8,
      time: "1分00秒",
      timeSec: 60,
      cost: "$0.09",
      costUsd: 0.09,
      note: "読み物向き",
    },
    claude: {
      quality: 10,
      time: "3分41秒",
      timeSec: 221,
      cost: "$1.08",
      costUsd: 1.08,
      note: "忠実性最高",
    },
  },
  app: {
    composer: {
      quality: 10,
      time: "47秒",
      timeSec: 47,
      cost: "$0.09",
      costUsd: 0.09,
      note: "三冠（本件）",
    },
    claude: {
      quality: 8,
      time: "2分34秒",
      timeSec: 154,
      cost: "$1.32",
      costUsd: 1.32,
      note: "数値混同に注意",
    },
  },
};

const APPROACH_LABELS: Record<string, string> = {
  marunage: "まるなげ",
  skill: "スキル",
  app: "アプリ",
};

const APPROACH_DESC: Record<string, string> = {
  marunage: "プロンプト丸投げ（SNS的AI社員に近い）",
  skill: "手順・品質基準をスキル化",
  app: "前処理をPythonで機械化",
};

function qualityTone(q: number): "success" | "warning" | "info" | "neutral" {
  if (q >= 10) return "success";
  if (q >= 8) return "info";
  if (q >= 7) return "warning";
  return "neutral";
}

function MatrixCell({
  cell,
  highlight,
}: {
  cell: Cell;
  highlight?: boolean;
}) {
  const theme = useHostTheme();
  return (
    <div
      style={{
        padding: 12,
        borderRadius: 8,
        border: `1px solid ${highlight ? theme.accent.primary : theme.stroke.primary}`,
        background: highlight ? theme.fill.secondary : theme.bg.elevated,
        minHeight: 132,
      }}
    >
      <Row gap={8} align="center" style={{ marginBottom: 8 }}>
        <Pill tone={qualityTone(cell.quality)} size="sm">
          品質 {cell.quality}/10
        </Pill>
        {highlight ? (
          <Pill tone="success" size="sm">
            推奨
          </Pill>
        ) : null}
      </Row>
      <Stack gap={4}>
        <Text weight="semibold">時間: {cell.time}</Text>
        <Text tone="secondary">コスト: {cell.cost}</Text>
        <Text tone="tertiary" size="small">
          {cell.note}
        </Text>
      </Stack>
    </div>
  );
}

export default function AiComparisonMatrix() {
  const theme = useHostTheme();

  const qualityChart = [
    { label: "まるなげ", composer: 6, claude: 7 },
    { label: "スキル", composer: 8, claude: 10 },
    { label: "アプリ", composer: 10, claude: 8 },
  ];

  const timeChart = [
    { label: "まるなげ", composer: 78, claude: 299 },
    { label: "スキル", composer: 60, claude: 221 },
    { label: "アプリ", composer: 47, claude: 154 },
  ];

  const costChart = [
    { label: "まるなげ", composer: 0.29, claude: 1.43 },
    { label: "スキル", composer: 0.09, claude: 1.08 },
    { label: "アプリ", composer: 0.09, claude: 1.32 },
  ];

  return (
    <Stack gap={24} style={{ padding: 24, maxWidth: 1100 }}>
      <Stack gap={8}>
        <H1>AI活用比較 — 1枚図</H1>
        <Text tone="secondary">
          方式 × モデル × 3指標（品質・時間・コスト）— 各組み合わせの最良試行
        </Text>
        <Text tone="tertiary" size="small">
          対象: YouTube koBLOf-53_g（71分・8セグメント） / 出典: app_manunage_comp02 実測（2026-07-16）
        </Text>
      </Stack>

      <Callout tone="info">
        争点は「モデルの高さ」より「仕事の渡し方」。丸投げ（まるなげ）は手軽だが、本件では品質・検証コストの面で最も割に合いにくかった。
      </Callout>

      <Grid columns={3} gap={12}>
        {(["marunage", "skill", "app"] as const).map((approach) => (
          <div key={approach}>
            <Card>
            <CardHeader
              trailing={
                approach === "app" ? (
                  <Pill tone="success" size="sm">
                    本件ベスト
                  </Pill>
                ) : approach === "marunage" ? (
                  <Pill tone="warning" size="sm">
                    要注意
                  </Pill>
                ) : null
              }
            >
              {APPROACH_LABELS[approach]}
            </CardHeader>
            <CardBody>
              <Text tone="secondary" size="small" style={{ marginBottom: 12 }}>
                {APPROACH_DESC[approach]}
              </Text>
              <Stack gap={10}>
                <div>
                  <Text tone="tertiary" size="small" weight="semibold">
                    Composer 2.5
                  </Text>
                  <Spacer size={6} />
                  <MatrixCell
                    cell={DATA[approach].composer}
                    highlight={approach === "app"}
                  />
                </div>
                <div>
                  <Text tone="tertiary" size="small" weight="semibold">
                    Claude Opus 4.8
                  </Text>
                  <Spacer size={6} />
                  <MatrixCell
                    cell={DATA[approach].claude}
                    highlight={approach === "skill"}
                  />
                </div>
              </Stack>
            </CardBody>
            </Card>
          </div>
        ))}
      </Grid>

      <Divider />

      <H2>3指標の一覧表</H2>
      <Table
        headers={["方式", "モデル", "品質", "時間", "コスト（参考）", "メモ"]}
        rows={[
          ["まるなげ", "Composer", "6/10", "1分18秒", "$0.29", "幻覚リスク"],
          ["まるなげ", "Claude", "7/10", "4分59秒", "$1.43", "最長"],
          ["スキル", "Composer", "8/10", "1分00秒", "$0.09", "読み物向き"],
          ["スキル", "Claude", "10/10", "3分41秒", "$1.08", "忠実性最高"],
          ["アプリ", "Composer", "10/10", "47秒", "$0.09", "三冠"],
          ["アプリ", "Claude", "8/10", "2分34秒", "$1.32", "数値混同注意"],
        ]}
        columnAlign={["left", "left", "center", "right", "right", "left"]}
        rowTone={[
          "warning",
          "warning",
          "info",
          "success",
          "success",
          "info",
        ]}
        striped
      />

      <Grid columns={3} gap={16}>
        <Stat label="最速（本件）" value="47秒" tone="success" />
        <Stat label="最高品質（Composer）" value="10/10" tone="success" />
        <Stat label="最低コスト（満点帯）" value="約$0.09" tone="success" />
      </Grid>

      <Card>
        <CardHeader>満点同士の比較（Composer アプリ vs Claude スキル）</CardHeader>
        <CardBody>
          <Table
            headers={["指標", "実測", "一般化", "今回に限ること"]}
            rows={[
              [
                "コスト",
                "約 1/12（$0.09 vs $1.08）",
                "短いタスクでも比率は維持されやすい",
                "First-party vs API の単価差",
              ],
              [
                "時間",
                "約 1/5（47秒 vs 3分41秒）",
                "Composer は速い傾向は残る",
                "71分・8セグメントで差が際立つ",
              ],
              ["品質", "同点 10/10", "方式設計が鍵", "—"],
            ]}
            columnAlign={["left", "left", "left", "left"]}
            striped
          />
          <Spacer size={12} />
          <Text tone="secondary" size="small">
            総時間 ≒ 固定コスト（起動・前処理など）＋ 文章量 × モデルの速さ。文章量が減ると倍率差は縮みやすい（短いタスクでは 1/3〜1/2 程度まで）。
          </Text>
        </CardBody>
      </Card>

      <Divider />

      <H2>指標別チャート</H2>
      <Text tone="tertiary" size="small">
        各方式の最良試行をモデル別に比較。品質は10点満点、時間は秒、コストはUSD参考見積もり。時間チャートは長尺動画（71分）前提。
      </Text>

      <Grid columns="1fr 1fr 1fr" gap={16}>
        <Stack gap={8}>
          <H3>品質（点）</H3>
          <BarChart
            categories={qualityChart.map((d) => d.label)}
            series={[
              { name: "Composer", data: qualityChart.map((d) => d.composer), tone: "info" },
              { name: "Claude", data: qualityChart.map((d) => d.claude), tone: "neutral" },
            ]}
            height={220}
          />
        </Stack>
        <Stack gap={8}>
          <H3>時間（秒）</H3>
          <BarChart
            categories={timeChart.map((d) => d.label)}
            series={[
              { name: "Composer", data: timeChart.map((d) => d.composer), tone: "info" },
              { name: "Claude", data: timeChart.map((d) => d.claude), tone: "neutral" },
            ]}
            height={220}
          />
        </Stack>
        <Stack gap={8}>
          <H3>コスト（USD）</H3>
          <BarChart
            categories={costChart.map((d) => d.label)}
            series={[
              { name: "Composer", data: costChart.map((d) => d.composer), tone: "info" },
              { name: "Claude", data: costChart.map((d) => d.claude), tone: "neutral" },
            ]}
            height={220}
            valuePrefix="$"
          />
        </Stack>
      </Grid>

      <Card>
        <CardHeader>読者向けの一言</CardHeader>
        <CardBody>
          <Stack gap={8}>
            <Text>
              強く言えるのは
              <Text as="span" weight="semibold" style={{ color: theme.accent.primary }}>
                {" "}
                安いモデル＋アプリで満点を、だいたい1/12のコストで出せる
              </Text>
              こと。速度の約1/5は同じく実測だが、長い動画・多い文章量の条件で差が大きく見えた。
            </Text>
            <Text tone="secondary">
              本件: Composer + アプリ（満点・47秒・約9セント） / 忠実性: Claude + スキル
            </Text>
            <Text tone="tertiary" size="small">
              2026年7月 Cursor First-party 利用枠2倍化 → コスト面の差はさらに有利に（時間倍率はタスク次第）。
            </Text>
          </Stack>
        </CardBody>
      </Card>
    </Stack>
  );
}
