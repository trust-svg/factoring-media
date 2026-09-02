import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { placeBid } from "./placeBid";
import { selectors } from "./selectors";

// テスト実行(dryRun)の経路を、Playwright 無しで確かめる。
//
// ここで一番確かめたいのは「DRY_RUN が返ったなら4点ガードを全部通っている」
// こと。止める位置がガード判定より **前** にずれると、確認画面に着けていない
// のに「テスト実行 成功」と報告され、本番でだけ壊れる。
// テスト実行の目的そのものが消えるので、位置を固定する。

const URL_ = "https://auctions.yahoo.co.jp/jp/auction/x1";
/** 2026-08-28 実測の確定ボタンの表示テキスト */
const SUBMIT_LABEL = "上記のガイドライン等、情報提供に同意して 入札する";

interface FakePage {
  clicks: string[];
  fills: Array<[string, string]>;
  /** page.goto に渡された URL(リトライで読み直しているかの確認用) */
  gotos: string[];
  // Page の代わりに placeBid へ渡す本体
  page: any;
}

function fakePage(
  o: {
    loginVisible?: boolean;
    /** 確認ボタンを押した後も入札額の入力欄が残っているか(=確認画面に着いていない) */
    formStillOpen?: boolean;
    submitFound?: boolean;
    submitLabel?: string;
    /** 確定ボタンが最初の「入札する」ボタンと同一要素か */
    sameElement?: boolean;
    /** ラベルが textContent ではなく value に入っている(`<input type=submit>` 型) */
    labelInValue?: boolean;
    /** 商品ページの「入札する」が見つからない(2026-09-02 の実入札と同じ状態) */
    bidFound?: boolean;
  } = {},
): FakePage {
  const clicks: string[] = [];
  const fills: Array<[string, string]> = [];
  const gotos: string[] = [];
  let confirmed = false;

  const bidHandle = { id: "bid" };
  const submitHandle = o.sameElement === true ? bidHandle : { id: "submit" };

  const priceInputCount = () => (confirmed && o.formStillOpen !== true ? 0 : 1);

  const loc = (sel: string) => {
    const self: any = {
      first: () => self,
      count: async () => {
        if (sel === selectors.priceInput) return priceInputCount();
        if (sel === selectors.bidSubmitButton) return o.submitFound === false ? 0 : 1;
        return 1;
      },
      isVisible: async () => sel === selectors.loginLink && o.loginVisible === true,
      fill: async (v: string) => {
        fills.push([sel, v]);
      },
      click: async () => {
        clicks.push(sel);
        if (sel === selectors.bidConfirmButton) confirmed = true;
      },
      textContent: async () => (sel === selectors.bidSubmitButton ? (o.submitLabel ?? SUBMIT_LABEL) : ""),
      // 実装はラベルを evaluate 経由で読む(`<input type=submit>` は value 側に入るため)
      evaluate: async (fn: any) => {
        const label = sel === selectors.bidSubmitButton ? (o.submitLabel ?? SUBMIT_LABEL) : "";
        return o.labelInValue === true
          ? fn({ value: label, textContent: "" })
          : fn({ value: "", textContent: label });
      },
      elementHandle: async () => {
        if (sel === selectors.bidSubmitButton) {
          if (o.submitFound === false) throw new Error("not found");
          return submitHandle;
        }
        if (sel === selectors.bidButton && o.bidFound === false) {
          // 実物の文言に合わせる(Playwright の Timeout メッセージ)
          throw new Error(
            `locator.elementHandle: Timeout 15000ms exceeded.\nCall log:\n  - waiting for locator('${sel}').first()`,
          );
        }
        return bidHandle;
      },
    };
    return self;
  };

  const page: any = {
    url: () => URL_,
    goto: async (u: string) => {
      gotos.push(u);
    },
    waitForLoadState: async () => {},
    evaluate: async (fn: any, args: any) => fn(args),
    locator: (sel: string) => loc(sel),
  };
  return { clicks, fills, gotos, page };
}

describe("placeBid のテスト実行(dryRun)", () => {
  it("確認画面まで進み、確定ボタンは押さずに DRY_RUN を返す", async () => {
    const f = fakePage();
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "DRY_RUN");
    assert.ok(
      !f.clicks.includes(selectors.bidSubmitButton),
      `確定ボタンを押してしまっている: ${JSON.stringify(f.clicks)}`,
    );
    // 途中までは本番と全く同じ手順を踏んでいること
    assert.ok(f.clicks.includes(selectors.bidButton), "入札ボタンを押していない");
    assert.ok(f.clicks.includes(selectors.bidConfirmButton), "確認ボタンを押していない");
    assert.deepEqual(f.fills, [[selectors.priceInput, "5000"]]);
  });

  it("dryRun でなければ確定ボタンを押して SUCCESS を返す", async () => {
    const f = fakePage();
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.equal(r.outcome, "SUCCESS");
    assert.ok(f.clicks.includes(selectors.bidSubmitButton), "確定ボタンを押していない");
  });

  it("テスト実行と本番で、確定クリック以外の手順が完全に一致する", async () => {
    const dry = fakePage();
    await placeBid(dry.page, URL_, 5_000, 1_000, { dryRun: true });
    const live = fakePage();
    await placeBid(live.page, URL_, 5_000, 1_000);
    assert.deepEqual(dry.fills, live.fills);
    assert.deepEqual(live.clicks, [...dry.clicks, selectors.bidSubmitButton]);
  });

  it("DRY_RUN の detail に、押すはずだったボタンと入札額が入る", async () => {
    const f = fakePage();
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "DRY_RUN");
    assert.ok("detail" in r && r.detail.includes(SUBMIT_LABEL), r.outcome);
    assert.ok("detail" in r && r.detail.includes("5000円"), "入札額が入っていない");
  });

  it("DRY_RUN の detail に、確定ボタンのセレクタのヒット数が入る", () => {
    // 2026-08-28 の失敗は2回とも「セレクタが0件」だった。テスト実行の目的は
    // 本番で押すはずのボタンが **ちょうど1件** だと先に確かめること。
    // 件数を出さないと、テスト実行が成功しても本番で緩いセレクタが裏の
    // ボタンを掴む余地(地雷12b)が残ったままになる。
    return placeBid(fakePage().page, URL_, 5_000, 1_000, { dryRun: true }).then((r) => {
      assert.ok("detail" in r && r.detail.includes("ヒット=1件"), r.outcome);
      assert.ok("detail" in r && !r.detail.includes("⚠️"), "1件なのに警告が出ている");
    });
  });

  it("ラベルが value にしか無くても(input[type=submit]) DRY_RUN まで通る", async () => {
    // 確認画面の確定ボタンがどの要素で描かれているかは未実測。
    // textContent だけを見ていると、正しく掴んでいるのにガードで落ちる。
    const f = fakePage({ labelInValue: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "DRY_RUN", "detail" in r ? r.detail : "");
    assert.ok("detail" in r && r.detail.includes(SUBMIT_LABEL));
  });

  // --- ここから「ガードを通っていないのに DRY_RUN を返さない」の確認 ---

  it("入札額の入力欄が残っていたら DRY_RUN ではなく PAGE_ERROR", async () => {
    const f = fakePage({ formStillOpen: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "PAGE_ERROR");
    assert.ok("detail" in r && r.detail.includes("確定を中止"), "中止理由が入っていない");
  });

  it("裏の商品ページのボタン(ラベルが「入札する」ちょうど)を掴んでいたら PAGE_ERROR", async () => {
    const f = fakePage({ submitLabel: "入札する" });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "PAGE_ERROR");
  });

  it("確定ボタンが見つからなければ PAGE_ERROR", async () => {
    const f = fakePage({ submitFound: false });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "PAGE_ERROR");
  });

  it("最初に押した入札ボタンと同一要素なら PAGE_ERROR", async () => {
    const f = fakePage({ sameElement: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "PAGE_ERROR");
  });

  it("ログインが切れていれば、テスト実行でも入札フォームを開かない", async () => {
    const f = fakePage({ loginVisible: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "SESSION_EXPIRED");
    assert.deepEqual(f.clicks, []);
  });
});

describe("入札ボタンを掴めなかったとき", () => {
  it("TIMEOUT を返し、detail に画面の実測を添える", async () => {
    // 2026-09-02 の実入札(k1242598835)は Timeout の1行だけを残して落ちた。
    // その1行では「文言が変わった / 描画が終わっていない / 商品ページに
    // 居ない」を切り分けられず、原因を知るにはオークションをもう1件使う
    // しかなかった。掴めなかった時点で押すのは諦めているので、
    // そこで画面を1往復計測して残す。
    const f = fakePage({ bidFound: false });
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.equal(r.outcome, "TIMEOUT");
    assert.ok("detail" in r && r.detail.includes("[入札ボタンの実測]"), "実測が添えられていない");
    // 元のエラーも消さない(どのセレクタで待っていたかが残る)
    assert.ok("detail" in r && r.detail.includes(selectors.bidButton), "待っていたセレクタが消えている");
    assert.deepEqual(f.clicks, [], "掴めていないのに何かを押している");
  });

  it("dryRun でも同じで、入札フォームには進まない", async () => {
    const f = fakePage({ bidFound: false });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "TIMEOUT");
    assert.deepEqual(f.fills, []);
  });
});

describe("リトライ時の読み直し", () => {
  it("reload:true なら URL が同じでも goto する", async () => {
    // ⚠️ 読み直さないリトライは、1回目と同じ DOM を触るので同じ理由で落ちる。
    // モーダルは URL を変えない(地雷11c)ので「URL が同じ = 同じ画面」でもない。
    const f = fakePage();
    await placeBid(f.page, URL_, 5_000, 1_000, { reload: true });
    assert.deepEqual(f.gotos, [URL_]);
  });

  it("reload を渡さなければ、URL が一致している限り goto しない", async () => {
    const f = fakePage();
    await placeBid(f.page, URL_, 5_000, 1_000);
    assert.deepEqual(f.gotos, []);
  });
});
