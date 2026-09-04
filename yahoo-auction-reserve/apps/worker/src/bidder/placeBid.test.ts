import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { placeBid } from "./placeBid";
import { selectors } from "./selectors";
import { CLICKABLE_SELECTOR } from "./settle";

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
  /** 描画待ちがクリック要素を数えた回数(=待ったかどうかの唯一の観測点) */
  settleProbes: () => number;
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
    /** 今開いているページが描画済みか(false = CSR がまだマウントしていない) */
    rendered?: boolean;
    /** 今開いているページの URL(別の商品ページに居る場合の確認用) */
    currentUrl?: string;
    /** 商品ページに「あなたが最高額入札者です」が出ているか */
    highestBidder?: boolean;
  } = {},
): FakePage {
  const clicks: string[] = [];
  const fills: Array<[string, string]> = [];
  const gotos: string[] = [];
  let confirmed = false;
  let settleProbes = 0;

  const bidHandle = { id: "bid" };
  const submitHandle = o.sameElement === true ? bidHandle : { id: "submit" };

  const priceInputCount = () => (confirmed && o.formStillOpen !== true ? 0 : 1);

  const loc = (sel: string) => {
    const self: any = {
      first: () => self,
      count: async () => {
        if (sel === selectors.priceInput) return priceInputCount();
        if (sel === selectors.bidSubmitButton) return o.submitFound === false ? 0 : 1;
        // 描画判定(renderVerdict)が見る2つ。実測の商品ページはクリック要素
        // 229個・入力欄11個(2026-09-03 コンテナ)。未マウントは3個程度。
        if (sel === CLICKABLE_SELECTOR) {
          settleProbes += 1;
          return o.rendered === false ? 3 : 229;
        }
        if (sel === "input") return o.rendered === false ? 0 : 11;
        return 1;
      },
      isVisible: async () => {
        if (sel === selectors.loginLink) return o.loginVisible === true;
        if (sel === selectors.highestBidderIndicator) return o.highestBidder === true;
        return false;
      },
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
    url: () => o.currentUrl ?? URL_,
    goto: async (u: string) => {
      gotos.push(u);
    },
    waitForLoadState: async () => {},
    // 描画待ちのポーリング間隔。テストでは待たない
    waitForTimeout: async () => {},
    evaluate: async (fn: any, args: any) => fn(args),
    locator: (sel: string) => loc(sel),
  };
  return { clicks, fills, gotos, settleProbes: () => settleProbes, page };
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

describe("読み直すかどうかの判定", () => {
  it("温めたページが同じ商品で描画済みなら goto しない", async () => {
    // ⚠️ ここが以前の欠陥。URL 一致で判定していたので、リダイレクト先に
    // 居る本番では条件が常に真になり、monitor がウォームアップで描画まで
    // 待ったページを入札の瞬間に毎回捨てて開き直していた。開き直した DOM は
    // CSR でほぼ空なので、15秒のセレクタ待ちがマウント時間ごと背負う。
    const f = fakePage();
    await placeBid(f.page, URL_, 5_000, 1_000);
    assert.deepEqual(f.gotos, []);
  });

  it("リダイレクト先(ホストが違う)に居ても、同じ商品なら goto しない", async () => {
    // 保存している URL は page.auctions… / 着地は auctions…(地雷14)。
    // URL の一致で判定する実装はここで必ず読み直してしまう。
    const f = fakePage({ currentUrl: "https://auctions.yahoo.co.jp/jp/auction/x1" });
    await placeBid(f.page, "https://page.auctions.yahoo.co.jp/jp/auction/x1", 5_000, 1_000);
    assert.deepEqual(f.gotos, []);
  });

  it("別の商品ページに居たら読み直す", async () => {
    const f = fakePage({ currentUrl: "https://auctions.yahoo.co.jp/jp/auction/zzz9" });
    await placeBid(f.page, URL_, 5_000, 1_000);
    assert.deepEqual(f.gotos, [URL_]);
  });

  it("描画されていなければ(CSR未マウント)読み直す", async () => {
    // 「同じ商品ページだから使い回す」だけだと、骨組みしか無いページを
    // そのまま掴んで15秒待つことになる。
    const f = fakePage({ rendered: false });
    await placeBid(f.page, URL_, 5_000, 1_000);
    assert.deepEqual(f.gotos, [URL_]);
  });

  it("reload:true なら描画済みの同じ商品ページでも goto する", async () => {
    // ⚠️ 読み直さないリトライは、1回目と同じ DOM を触るので同じ理由で落ちる。
    // モーダルは URL を変えない(地雷11c)ので「URL が同じ = 同じ画面」でもない。
    const f = fakePage();
    await placeBid(f.page, URL_, 5_000, 1_000, { reload: true });
    assert.deepEqual(f.gotos, [URL_]);
  });
});

describe("読み直した後の描画待ち", () => {
  // ⚠️ 「待ったかどうか」は結果からは見えない(フェイクの描画はすぐ落ち着く
  // ので、予算を無視しても outcome は変わらない)。数えているのは
  // 描画待ちがクリック要素を数えた回数。reload:true のときは、この
  // カウントが増えるのは settlePage の中だけ。

  it("残り時間が十分あれば、読み直した後に描画を待つ", async () => {
    const f = fakePage();
    await placeBid(f.page, URL_, 5_000, 1_000, { reload: true, remainingMs: 60_000 });
    assert.ok(f.settleProbes() > 0, "読み直したのに描画を待っていない");
  });

  it("残り時間が入札の手順ぶんしか無ければ、描画を待たずに入札へ進む", async () => {
    // ⚠️ ここを待つと、5秒前入札の予約が待っている間に終わる。
    const f = fakePage();
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { reload: true, remainingMs: 2_000 });
    assert.equal(f.settleProbes(), 0, "残り時間が無いのに描画を待っている");
    // 描画は諦めたが、入札そのものは実行されている
    assert.equal(r.outcome, "SUCCESS", "detail" in r ? r.detail : r.outcome);
    assert.ok(f.clicks.includes(selectors.bidButton), "入札を試みていない");
  });

  it("入札ボタンを掴めなかったときの detail に、描画待ちの実測が入る", async () => {
    const f = fakePage({ bidFound: false });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { reload: true });
    assert.equal(r.outcome, "TIMEOUT");
    assert.ok("detail" in r && r.detail.includes("[描画待ち]"), "描画の実測が無い");
  });
});

// ヤフオクは自動入札(代理入札)なので、自分が最高額入札者のまま上限だけ上げても
// 現在価格は動かず、得るものが無いのに取り消せない操作だけが残る。
// 2026-09-04 の d1242748141 は、手動入札済みの商品で入口ボタンが
// 「値段を上げて入札」に変わっていた(selectors.ts の地雷15)。
describe("すでに自分が最高額入札者だったとき", () => {
  it("入札ボタンに触れずに ALREADY_HIGHEST を返す", async () => {
    const f = fakePage({ highestBidder: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.equal(r.outcome, "ALREADY_HIGHEST");
    // ⚠️ 「クリックしていない」だけでは足りない。入力欄に額を入れた時点で
    //    フォームが開いている = 押せる状態まで進んでいる。
    assert.deepEqual(f.clicks, [], `何かを押している: ${JSON.stringify(f.clicks)}`);
    assert.deepEqual(f.fills, [], `入札額を入れている: ${JSON.stringify(f.fills)}`);
  });

  it("dryRun でも同じ(テスト実行が本番と違う判断をしない)", async () => {
    const f = fakePage({ highestBidder: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000, { dryRun: true });
    assert.equal(r.outcome, "ALREADY_HIGHEST");
    assert.deepEqual(f.clicks, []);
  });

  it("detail に予定額が入る(いくら入れようとしたのかが後から分かる)", async () => {
    const f = fakePage({ highestBidder: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.ok("detail" in r && r.detail.includes("5000"), `detail: ${JSON.stringify(r)}`);
  });

  // ⚠️ 順序が逆だと、ログインが切れて商品ページすら出ていない状態で
  //    「最高額入札者ではない」と読んで入札に進む。切れているのだから
  //    入札できるはずがなく、原因が SESSION_EXPIRED ではなく
  //    Timeout として記録されて切り分けが遅れる。
  it("ログイン切れの判定の方が先", async () => {
    const f = fakePage({ highestBidder: true, loginVisible: true });
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.equal(r.outcome, "SESSION_EXPIRED");
  });

  // ⚠️ 判定できなかったときは入札する側に倒す。最高額表示を読めないことを
  //    理由に入札を見送ると、予約が静かに空振りする(こちらの方が損害が大きい)。
  it("最高額表示の判定が例外を投げたら、止めずに入札へ進む", async () => {
    const f = fakePage();
    const orig = f.page.locator;
    f.page.locator = (sel: string) => {
      const l = orig(sel);
      if (sel === selectors.highestBidderIndicator) {
        return { ...l, first: () => ({ isVisible: async () => { throw new Error("detached"); } }) };
      }
      return l;
    };
    const r = await placeBid(f.page, URL_, 5_000, 1_000);
    assert.equal(r.outcome, "SUCCESS");
  });
});
