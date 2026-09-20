/* Punjaber — a small hash-routed SPA over the course API. No build step. */

(function () {
  "use strict";

  var view = document.getElementById("view");
  var dueBadge = document.getElementById("due-badge");
  var settings = { script: "both", gender: "male", audio: true, daily_goal: 20 };

  // --- utilities ----------------------------------------------------------

  function profile() {
    var name = localStorage.getItem("punjaber.user");
    if (!name) {
      name = "local";
      localStorage.setItem("punjaber.user", name);
    }
    return name;
  }

  function api(path, options) {
    options = options || {};
    return fetch("/api" + path, {
      method: options.method || "GET",
      headers: {
        "Content-Type": "application/json",
        "X-Punjaber-User": profile()
      },
      body: options.body ? JSON.stringify(options.body) : undefined
    }).then(function (response) {
      if (!response.ok) {
        return response.json().catch(function () { return {}; }).then(function (payload) {
          throw new Error(payload.detail || "Request failed (" + response.status + ")");
        });
      }
      return response.json();
    });
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
    });
  }

  function el(html) {
    var wrap = document.createElement("div");
    wrap.innerHTML = html.trim();
    return wrap.firstElementChild;
  }

  function render(html) {
    view.innerHTML = html;
    window.scrollTo(0, 0);
  }

  function on(selector, event, handler, root) {
    (root || view).querySelectorAll(selector).forEach(function (node) {
      node.addEventListener(event, handler);
    });
  }

  // Respect the learner's script preference without losing the audio text.
  function showPa(item) { return settings.script === "roman" ? "" : item.pa; }
  function showRoman(item) { return settings.script === "gurmukhi" ? "" : item.roman; }

  // --- speech -------------------------------------------------------------
  //
  // Audio comes from the server by default: espeak-ng renders the Gurmukhi to
  // a WAV, which plays identically in every browser. Browser speech synthesis
  // is used only when a genuine Punjabi voice exists (Edge has one), because
  // the alternative was a Hindi voice being handed a script it cannot read.

  var browserVoice = null;
  var offlineAudio = true;
  // A public deployment turns the studio off, since the app has no logins and
  // its upload endpoint would otherwise be open to anyone.
  var studioEnabled = true;
  var player = new Audio();

  // Texts that have a native-speaker recording behind them. Loaded once at
  // startup so playback knows, without a round trip, whether it is about to
  // play a real voice — which changes how "slow" has to work.
  var recordedTexts = {};

  function isRecorded(text) {
    return Object.prototype.hasOwnProperty.call(recordedTexts, text);
  }

  function loadRecordingManifest() {
    return api("/recordings").then(function (data) {
      recordedTexts = {};
      data.texts.forEach(function (text) { recordedTexts[text] = true; });
    }).catch(function () {});
  }

  function pickVoice() {
    if (!("speechSynthesis" in window)) return;
    var voices = window.speechSynthesis.getVoices() || [];
    // Punjabi only. A Hindi voice cannot read Gurmukhi, so it is not a fallback.
    browserVoice = voices.filter(function (v) {
      return (v.lang || "").toLowerCase().indexOf("pa") === 0;
    })[0] || null;
  }

  function listVoices() {
    if (!("speechSynthesis" in window)) return [];
    return (window.speechSynthesis.getVoices() || []).map(function (v) {
      return v.name + " (" + v.lang + ")";
    });
  }

  if ("speechSynthesis" in window) {
    pickVoice();
    // Voices load asynchronously, and in Chromium often arrive empty first.
    window.speechSynthesis.addEventListener("voiceschanged", pickVoice);
  }

  function usingBrowserVoice() {
    var source = settings.voice_source || "auto";
    if (source === "offline") return false;
    if (source === "browser") return !!browserVoice;
    return !!browserVoice; // auto: only when a real Punjabi voice is installed
  }

  function speakViaBrowser(text, slow) {
    var synth = window.speechSynthesis;
    synth.cancel();
    // Chromium jams its queue when cancel() and speak() land in the same tick,
    // which is why the icon could look dead. A tick's gap avoids it.
    setTimeout(function () {
      var utterance = new SpeechSynthesisUtterance(text);
      utterance.voice = browserVoice;
      utterance.lang = browserVoice.lang;
      utterance.rate = slow ? 0.55 : 0.85;
      synth.speak(utterance);
    }, 60);
  }

  function speakViaServer(text, slow) {
    var recorded = isRecorded(text);
    player.pause();
    // A recording has no slow variant to render, so slow it on playback. The
    // synthesiser does a better job re-articulating, so let it do the work.
    player.playbackRate = (slow && recorded) ? 0.6 : 1;
    player.src = "/api/speech?text=" + encodeURIComponent(text) +
      (slow && !recorded ? "&speed=slow" : "");
    var started = player.play();
    // Autoplay policies reject this when there has been no user gesture yet.
    // The manual buttons still work, so failing quietly is the right response.
    if (started && started.catch) started.catch(function () {});
  }

  function speak(text, slow) {
    if (!settings.audio || !text) return;
    // A native recording beats every synthesiser, including a good browser one.
    if (isRecorded(text)) return speakViaServer(text, slow);
    if (usingBrowserVoice()) return speakViaBrowser(text, slow);
    if (offlineAudio) return speakViaServer(text, slow);
    if (browserVoice) return speakViaBrowser(text, slow);
  }

  function speakButton(text, withSlow) {
    var buttons =
      '<button class="speak-btn" data-speak="' + esc(text) + '" title="Listen" aria-label="Listen">🔊</button>';
    if (withSlow) {
      buttons +=
        '<button class="speak-btn" data-speak-slow="' + esc(text) +
        '" title="Listen slowly" aria-label="Listen slowly">🐢</button>';
    }
    return buttons;
  }

  function wireSpeak(root) {
    on("[data-speak]", "click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      speak(event.currentTarget.getAttribute("data-speak"), false);
    }, root);
    on("[data-speak-slow]", "click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      speak(event.currentTarget.getAttribute("data-speak-slow"), true);
    }, root);
  }

  // --- home ---------------------------------------------------------------

  function lessonRow(lesson) {
    var mark = lesson.status === "passed" ? "✓" : lesson.status === "locked" ? "🔒" : "▶";
    var meta = lesson.status === "passed"
      ? Math.round(lesson.best_score * 100) + "%"
      : lesson.item_count + " words";
    return '' +
      '<button class="lesson ' + lesson.status + '" data-lesson="' + esc(lesson.id) + '"' +
      (lesson.status === "locked" ? " disabled" : "") + '>' +
        '<span class="lesson-dot">' + mark + "</span>" +
        '<span class="lesson-body">' +
          '<span class="lesson-title">' + esc(lesson.title) + "</span><br>" +
          '<span class="lesson-goal">' + esc(lesson.goal) + "</span>" +
        "</span>" +
        '<span class="lesson-meta">' + esc(meta) + (lesson.has_dialogue ? "<br>💬" : "") + "</span>" +
      "</button>";
  }

  function viewHome() {
    return api("/course").then(function (data) {
      var s = data.summary;
      var units = data.units.map(function (unit) {
        return '' +
          '<section class="unit">' +
            '<div class="unit-head">' +
              '<span class="unit-num' + (unit.optional ? " optional" : "") + '">' +
                (unit.optional ? "Primer · optional" : "Unit " + unit.order) + "</span>" +
              "<h2>" + esc(unit.title) + "</h2>" +
              '<span class="unit-count">' + unit.passed + " / " + unit.total + "</span>" +
            "</div>" +
            '<p class="sub tiny" style="margin-bottom:10px">' + esc(unit.description) + "</p>" +
            '<div class="lesson-list">' + unit.lessons.map(lessonRow).join("") + "</div>" +
          "</section>";
      }).join("");

      var cta = s.next_lesson
        ? '<button class="btn btn-primary" data-lesson="' + esc(s.next_lesson) + '">Continue learning</button>'
        : '<span class="muted">Course complete — keep reviewing!</span>';

      render('' +
        '<div class="hero">' +
          "<div>" +
            "<h1>Learn conversational Punjabi</h1>" +
            '<p class="sub">Ten units, thirty lessons, one small step at a time.</p>' +
            '<div class="btn-row">' + cta +
              (s.due_count ? '<a class="btn" href="#/review">Review ' + s.due_count + " due</a>" : "") +
            "</div>" +
          "</div>" +
          '<div class="hero-stats">' +
            '<div><div class="stat-value">' + s.percent + '%</div><div class="stat-label">Course</div></div>' +
            '<div><div class="stat-value">' + s.streak + '</div><div class="stat-label">Day streak</div></div>' +
            '<div><div class="stat-value">' + s.lessons_passed + "/" + s.lessons_total + '</div><div class="stat-label">Lessons</div></div>' +
          "</div>" +
        "</div>" +
        '<div class="progressbar" style="margin-bottom:26px"><i style="width:' + s.percent + '%"></i></div>' +
        units);

      dueBadge.hidden = !s.due_count;
      dueBadge.textContent = s.due_count;

      on("[data-lesson]", "click", function (event) {
        var id = event.currentTarget.getAttribute("data-lesson");
        location.hash = "#/lesson/" + id;
      });
    });
  }

  // --- lesson: teaching stage --------------------------------------------

  function viewLesson(lessonId) {
    return api("/lessons/" + encodeURIComponent(lessonId)).then(function (lesson) {
      if (lesson.locked) {
        render('<div class="empty"><h1>Locked</h1><p>Finish the previous lesson to open this one.</p>' +
               '<a class="btn" href="#/">Back to the course</a></div>');
        return;
      }
      teachStage(lesson, 0);
    });
  }

  function stepper(active) {
    var steps = ["Learn", "Practice", "Result"];
    return '<div class="stepper">' + steps.map(function (name, i) {
      return '<span class="step' + (i === active ? " on" : "") + '">' + name + "</span>";
    }).join('<span>›</span>') + "</div>";
  }

  function teachStage(lesson, index) {
    var items = lesson.items;

    if (index >= items.length) {
      return teachRecap(lesson);
    }

    var item = items[index];
    var percent = Math.round((index / items.length) * 100);

    render('' +
      stepper(0) +
      "<h1>" + esc(lesson.title) + "</h1>" +
      '<p class="sub">' + esc(lesson.goal) + "</p>" +
      '<div class="drill-top"><div class="progressbar"><i style="width:' + percent + '%"></i></div>' +
        '<span class="tiny muted">' + (index + 1) + " / " + items.length + "</span></div>" +
      '<div class="card flashcard">' +
        (showPa(item) ? '<div class="flash-pa">' + esc(item.pa) + "</div>" : "") +
        (showRoman(item) ? '<div class="flash-roman">' + esc(item.roman) + "</div>" : "") +
        '<div class="flash-en">' + esc(item.en) + "</div>" +
        '<div style="margin-top:6px">' + speakButton(item.pa, true) + "</div>" +
        (item.say ? '<div class="flash-say">' + esc(item.say) + "</div>" : "") +
        (item.note ? '<div class="flash-note">' + esc(item.note) + "</div>" : "") +
      "</div>" +
      '<div class="btn-row" style="margin-top:18px">' +
        (index > 0 ? '<button class="btn" id="back">Back</button>' : "") +
        '<button class="btn btn-primary" id="next">' +
          (index === items.length - 1 ? "See the notes" : "Next word") + "</button>" +
        '<a class="btn btn-ghost" href="#/">Leave</a>' +
      "</div>");

    wireSpeak(view);
    speak(item.pa);

    var next = document.getElementById("next");
    if (next) next.addEventListener("click", function () { teachStage(lesson, index + 1); });
    var back = document.getElementById("back");
    if (back) back.addEventListener("click", function () { teachStage(lesson, index - 1); });
  }

  function teachRecap(lesson) {
    var notes = (lesson.notes || []).map(function (note) {
      return '<div class="note">' + esc(note) + "</div>";
    }).join("");

    var dialogue = (lesson.dialogue || []).map(function (turn) {
      var mine = /you/i.test(turn.speaker);
      return '' +
        '<div class="turn' + (mine ? " you" : "") + '">' +
          '<div class="turn-who">' + esc(turn.speaker) + " " + speakButton(turn.pa, true) + "</div>" +
          (showPa(turn) ? '<div class="turn-pa">' + esc(turn.pa) + "</div>" : "") +
          (showRoman(turn) ? '<div class="turn-roman">' + esc(turn.roman) + "</div>" : "") +
          '<div class="turn-en">' + esc(turn.en) + "</div>" +
        "</div>";
    }).join("");

    render('' +
      stepper(0) +
      "<h1>" + esc(lesson.title) + "</h1>" +
      '<p class="sub">Read these before you drill — they explain the pattern.</p>' +
      (notes ? '<div class="notes">' + notes + "</div>" : "") +
      (dialogue ? "<h2 style=\"margin-top:22px\">See it in a conversation</h2>" +
                  '<div class="dialogue">' + dialogue + "</div>" : "") +
      '<div class="btn-row" style="margin-top:20px">' +
        '<button class="btn btn-primary" id="start">Start practice</button>' +
        '<button class="btn" id="again">Review the words</button>' +
        '<a class="btn btn-ghost" href="#/">Leave</a>' +
      "</div>");

    wireSpeak(view);
    document.getElementById("start").addEventListener("click", function () {
      startLessonPractice(lesson);
    });
    document.getElementById("again").addEventListener("click", function () {
      teachStage(lesson, 0);
    });
  }

  // --- the drill engine ---------------------------------------------------

  function startLessonPractice(lesson) {
    render('<div class="loading">Building your practice…</div>');
    api("/lessons/" + encodeURIComponent(lesson.id) + "/practice").then(function (data) {
      runDrill({
        title: lesson.title,
        exercises: data.exercises,
        step: 1,
        onFinish: function (session) {
          finishLesson(lesson, session);
        }
      });
    }).catch(showError);
  }

  function runDrill(config) {
    var session = { index: 0, correct: 0, missed: [], startedAt: 0 };
    var exercises = config.exercises;

    if (!exercises.length) {
      render('<div class="empty"><h1>Nothing to practise</h1>' +
             '<p>Finish a lesson first and its words will show up here for review.</p>' +
             '<a class="btn btn-primary" href="#/">Back to the course</a></div>');
      return;
    }

    function step() {
      if (session.index >= exercises.length) {
        return config.onFinish(session);
      }
      renderExercise(exercises[session.index]);
    }

    function renderExercise(exercise) {
      var percent = Math.round((session.index / exercises.length) * 100);
      var body;

      if (exercise.kind === "assemble") {
        body = '' +
          '<div class="assembly" id="assembly"></div>' +
          '<div class="tiles" id="tiles">' + exercise.tiles.map(function (word, i) {
            return '<button class="tile" data-tile="' + i + '">' + esc(word) + "</button>";
          }).join("") + "</div>" +
          '<div class="btn-row" style="margin-top:16px">' +
            '<button class="btn btn-primary" id="submit">Check</button>' +
            '<button class="btn" id="clear">Clear</button>' +
          "</div>";
      } else if (exercise.kind === "type_roman") {
        body = '' +
          '<input class="type-input" id="typed" autocomplete="off" autocapitalize="off" ' +
          'autocorrect="off" spellcheck="false" placeholder="type the romanised Punjabi…">' +
          '<div class="btn-row" style="margin-top:16px">' +
            '<button class="btn btn-primary" id="submit">Check</button>' +
            '<button class="btn" id="skip">Skip</button>' +
          "</div>";
      } else {
        body = '<div class="choices">' + exercise.choices.map(function (choice) {
          var isPa = exercise.kind === "en_to_pa" || exercise.kind === "minimal_pair";
          return '' +
            '<button class="choice" data-key="' + esc(choice.key) + '">' +
              '<span class="c-main' + (isPa ? " pa" : "") + '">' + esc(choice.text) + "</span>" +
              (choice.sub ? '<span class="c-sub">' + esc(choice.sub) + "</span>" : "") +
            "</button>";
        }).join("") + "</div>";
      }

      var promptHtml;
      if (exercise.kind === "listen" || exercise.kind === "minimal_pair") {
        var hint = exercise.kind === "minimal_pair"
          ? "These differ by one sound. Use 🐢 to slow it down."
          : "Tap to hear it again";
        promptHtml = '<div style="font-size:44px">' + speakButton(exercise.speak, true) + "</div>" +
                     '<div class="tiny muted" style="margin-top:8px">' + hint + "</div>";
      } else {
        var isPaPrompt = exercise.kind === "pa_to_en";
        promptHtml =
          '<div class="prompt-main' + (isPaPrompt ? " pa" : "") + '">' + esc(exercise.prompt.main) +
            (isPaPrompt ? " " + speakButton(exercise.speak) : "") + "</div>" +
          (exercise.prompt.sub && settings.script !== "gurmukhi"
            ? '<div class="prompt-sub">' + esc(exercise.prompt.sub) + "</div>" : "");
      }

      render('' +
        stepper(config.step) +
        '<div class="drill-top">' +
          '<div class="progressbar"><i style="width:' + percent + '%"></i></div>' +
          '<span class="tiny muted">' + (session.index + 1) + " / " + exercises.length + "</span>" +
        "</div>" +
        '<div class="card">' +
          '<div class="prompt-block">' +
            '<div class="instruction">' + esc(exercise.instruction) + "</div>" +
            promptHtml +
          "</div>" +
          body +
          '<div id="feedback"></div>' +
        "</div>" +
        '<div class="btn-row" style="margin-top:16px"><a class="btn btn-ghost" href="#/">Leave</a></div>');

      wireSpeak(view);
      session.startedAt = Date.now();
      if (exercise.kind === "listen" || exercise.kind === "minimal_pair") speak(exercise.speak);

      if (exercise.kind === "assemble") {
        wireAssemble(exercise);
      } else if (exercise.kind === "type_roman") {
        wireTyping(exercise);
      } else {
        on(".choice", "click", function (event) {
          var key = event.currentTarget.getAttribute("data-key");
          grade(exercise, { correct: key === exercise.answer_key }, event.currentTarget);
        });
      }
    }

    function wireAssemble(exercise) {
      var picked = [];
      var assembly = document.getElementById("assembly");

      function redraw() {
        assembly.innerHTML = picked.map(function (index) {
          return '<button class="tile" data-picked="' + index + '">' + esc(exercise.tiles[index]) + "</button>";
        }).join("");
        view.querySelectorAll("#tiles .tile").forEach(function (tile) {
          var index = Number(tile.getAttribute("data-tile"));
          tile.classList.toggle("used", picked.indexOf(index) !== -1);
        });
        on("[data-picked]", "click", function (event) {
          var index = Number(event.currentTarget.getAttribute("data-picked"));
          picked = picked.filter(function (i) { return i !== index; });
          redraw();
        }, assembly);
      }

      on("#tiles .tile", "click", function (event) {
        var index = Number(event.currentTarget.getAttribute("data-tile"));
        if (picked.indexOf(index) === -1) picked.push(index);
        redraw();
      });
      document.getElementById("clear").addEventListener("click", function () {
        picked = [];
        redraw();
      });
      document.getElementById("submit").addEventListener("click", function () {
        var given = picked.map(function (i) { return exercise.tiles[i]; }).join(" ");
        grade(exercise, { given: given });
      });
      redraw();
    }

    function wireTyping(exercise) {
      var input = document.getElementById("typed");
      input.focus();
      function submit() { grade(exercise, { given: input.value }); }
      input.addEventListener("keydown", function (event) {
        if (event.key === "Enter") submit();
      });
      document.getElementById("submit").addEventListener("click", submit);
      document.getElementById("skip").addEventListener("click", function () {
        grade(exercise, { given: "" });
      });
    }

    function grade(exercise, answer, node) {
      var payload = {
        item_id: exercise.item_id,
        kind: exercise.kind,
        elapsed_ms: Date.now() - session.startedAt
      };
      if (answer.given !== undefined) payload.given = answer.given;
      else payload.correct = answer.correct;

      // Lock the UI immediately so a double tap cannot answer twice.
      view.querySelectorAll(".choice, .tile, #submit, #skip, #clear").forEach(function (n) {
        n.disabled = true;
      });

      api("/attempts", { method: "POST", body: payload }).then(function (result) {
        if (result.correct) session.correct += 1;
        else session.missed.push(exercise.reveal);

        if (node) node.classList.add(result.correct ? "correct" : "wrong");
        if (!result.correct && exercise.answer_key) {
          var right = view.querySelector('.choice[data-key="' + exercise.answer_key + '"]');
          if (right) right.classList.add("correct");
        }
        showFeedback(exercise, result);
      }).catch(showError);
    }

    function showFeedback(exercise, result) {
      var box = document.getElementById("feedback");
      var last = session.index === exercises.length - 1;
      box.innerHTML = '' +
        '<div class="feedback ' + (result.correct ? "ok" : "no") + '">' +
          '<div class="feedback-head">' + (result.correct ? "Correct" : "Not quite") + "</div>" +
          '<div class="pa">' + esc(result.expected.pa) + " " + speakButton(result.expected.pa) + "</div>" +
          '<div><strong>' + esc(result.expected.roman) + "</strong> — " + esc(result.expected.en) + "</div>" +
        "</div>" +
        '<div class="btn-row" style="margin-top:14px">' +
          '<button class="btn btn-primary" id="continue">' + (last ? "Finish" : "Continue") + "</button>" +
        "</div>";

      wireSpeak(box);
      speak(result.expected.pa);

      // Enter also continues. The handler must be torn down whichever way the
      // learner advances, or a stale one would skip the following exercise.
      function onKey(event) {
        if (event.key === "Enter") advance();
      }
      function advance() {
        document.removeEventListener("keydown", onKey);
        session.index += 1;
        step();
      }
      document.getElementById("continue").addEventListener("click", advance);
      document.addEventListener("keydown", onKey);
    }

    step();
  }

  // --- results ------------------------------------------------------------

  function missedList(missed) {
    if (!missed.length) return "";
    var seen = {};
    var rows = missed.filter(function (item) {
      if (seen[item.roman]) return false;
      seen[item.roman] = true;
      return true;
    }).map(function (item) {
      return '<div class="missed-row">' + speakButton(item.pa) +
        '<span class="pa" style="font-size:19px">' + esc(item.pa) + "</span>" +
        "<span><strong>" + esc(item.roman) + "</strong> — " + esc(item.en) + "</span></div>";
    }).join("");
    return "<h2 style=\"margin-top:26px\">Worth another look</h2>" + '<div class="missed">' + rows + "</div>";
  }

  function finishLesson(lesson, session) {
    var total = session.correct + session.missed.length;
    api("/lessons/" + encodeURIComponent(lesson.id) + "/complete", {
      method: "POST",
      body: { correct: session.correct, total: total }
    }).then(function (result) {
      var percent = Math.round(result.score * 100);
      var next = result.unlocked_next || lesson.next_lesson;

      render('' +
        stepper(2) +
        '<div class="card result ' + (result.passed ? "pass" : "fail") + '">' +
          '<div class="result-score">' + percent + "%</div>" +
          "<h1>" + (result.passed ? "Lesson passed" : "Nearly there") + "</h1>" +
          '<p class="sub" style="margin:0">' +
            (result.passed
              ? "You scored " + session.correct + " of " + total + ". The next lesson is unlocked."
              : "You need " + Math.round(result.threshold * 100) + "% to move on. Run it again — it sticks faster the second time.") +
          "</p>" +
          '<div class="btn-row" style="justify-content:center;margin-top:10px">' +
            (result.passed && next
              ? '<button class="btn btn-primary" data-go="#/lesson/' + esc(next) + '">Next lesson</button>'
              : '<button class="btn btn-primary" data-go="#/lesson/' + esc(lesson.id) + '">Try again</button>') +
            '<button class="btn" data-go="#/">Back to the course</button>' +
          "</div>" +
          (result.streak ? '<p class="tiny muted" style="margin:8px 0 0">' + result.streak + "-day streak 🔥</p>" : "") +
        "</div>" +
        missedList(session.missed));

      wireSpeak(view);
      on("[data-go]", "click", function (event) {
        location.hash = event.currentTarget.getAttribute("data-go");
        if (location.hash === "#/lesson/" + lesson.id) route();
      });
    }).catch(showError);
  }

  // --- review -------------------------------------------------------------

  function viewReview() {
    render('<div class="loading">Gathering your review…</div>');
    return api("/review?limit=15").then(function (data) {
      if (!data.exercises.length) {
        render('<div class="empty"><h1>Nothing due</h1>' +
               "<p>Words come back here on a spaced schedule once you have met them in a lesson.</p>" +
               '<a class="btn btn-primary" href="#/">Back to the course</a></div>');
        return;
      }
      runDrill({
        title: "Review",
        exercises: data.exercises,
        step: 1,
        onFinish: function (session) {
          var total = session.correct + session.missed.length;
          render('' +
            '<div class="card result pass">' +
              '<div class="result-score">' + Math.round((session.correct / total) * 100) + "%</div>" +
              "<h1>Review done</h1>" +
              '<p class="sub" style="margin:0">' + session.correct + " of " + total +
                " right. These words are now scheduled further out.</p>" +
              '<div class="btn-row" style="justify-content:center;margin-top:10px">' +
                '<a class="btn btn-primary" href="#/">Back to the course</a>' +
                '<button class="btn" id="more">Another round</button>' +
              "</div>" +
            "</div>" +
            missedList(session.missed));
          wireSpeak(view);
          document.getElementById("more").addEventListener("click", viewReview);
        }
      });
    });
  }

  // --- progress -----------------------------------------------------------

  function viewProgress() {
    return api("/stats").then(function (s) {
      var byDay = {};
      s.activity.forEach(function (row) { byDay[row.day] = row.answers; });

      var cells = [];
      for (var i = 29; i >= 0; i--) {
        var day = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
        var n = byDay[day] || 0;
        var level = n === 0 ? "" : n < 10 ? "l1" : n < 25 ? "l2" : "l3";
        cells.push('<i class="' + level + '" title="' + day + ": " + n + ' answers"></i>');
      }

      var trouble = s.trouble_words.length
        ? '<div class="missed">' + s.trouble_words.map(function (word) {
            return '<div class="missed-row">' + speakButton(word.pa) +
              '<span class="pa" style="font-size:19px">' + esc(word.pa) + "</span>" +
              "<span><strong>" + esc(word.roman) + "</strong> — " + esc(word.en) + "</span>" +
              '<span class="tiny muted" style="margin-left:auto">' + word.n_wrong + " misses</span></div>";
          }).join("") + "</div>"
        : '<p class="muted tiny">No trouble spots yet.</p>';

      function tile(value, label) {
        return '<div class="card"><div class="stat-value">' + value + '</div><div class="stat-label">' + label + "</div></div>";
      }

      render('' +
        "<h1>Your progress</h1>" +
        '<p class="sub">Everything is stored locally in the container\'s database.</p>' +
        '<div class="grid-stats">' +
          tile(s.lessons_passed + "/" + s.lessons_total, "Lessons passed") +
          tile(s.words_known + "/" + s.words_total, "Words learned") +
          tile(Math.round(s.accuracy * 100) + "%", "Accuracy") +
          tile(s.streak, "Day streak") +
          tile(s.due_count, "Due for review") +
          tile(s.answers, "Answers given") +
        "</div>" +
        '<div class="card"><h2>Last 30 days</h2>' +
          '<p class="tiny muted" style="margin:0">Each square is a day of practice.</p>' +
          '<div class="heat">' + cells.join("") + "</div></div>" +
        "<h2 style=\"margin-top:26px\">Words you keep missing</h2>" + trouble);

      wireSpeak(view);
    });
  }

  // --- settings -----------------------------------------------------------

  function voiceSummary() {
    var parts = [];
    parts.push(offlineAudio
      ? "Built-in offline voice: available."
      : "Built-in offline voice: not installed in this container.");
    parts.push(browserVoice
      ? "Browser Punjabi voice: " + browserVoice.name + "."
      : "Browser Punjabi voice: none found (" + listVoices().length + " other voices installed).");
    return parts.join(" ");
  }

  function viewSettings() {
    return api("/settings").then(function (current) {
      settings = current;
      function option(value, label, selected) {
        return '<option value="' + value + '"' + (selected === value ? " selected" : "") + ">" + label + "</option>";
      }

      render('' +
        "<h1>Settings</h1>" +
        '<p class="sub">These change how words are shown and spoken.</p>' +
        '<div class="card">' +
          '<div class="field"><label for="script">Script shown</label>' +
            '<select id="script">' +
              option("both", "Gurmukhi and romanised", current.script) +
              option("gurmukhi", "Gurmukhi only (harder)", current.script) +
              option("roman", "Romanised only (easier)", current.script) +
            "</select></div>" +
          '<div class="field"><label for="gender">You speak as</label>' +
            '<select id="gender">' +
              option("male", "Male (…karda han)", current.gender) +
              option("female", "Female (…kardi han)", current.gender) +
            "</select>" +
            '<span class="tiny muted">Punjabi verbs change with the speaker\'s gender.</span></div>' +
          '<div class="field"><label for="audio">Audio</label>' +
            '<select id="audio">' +
              option("true", "Speak words aloud", String(current.audio)) +
              option("false", "Silent", String(current.audio)) +
            "</select></div>" +
          '<div class="field"><label for="voice_source">Voice</label>' +
            '<select id="voice_source">' +
              option("auto", "Automatic (recommended)", current.voice_source) +
              option("offline", "Built-in offline voice", current.voice_source) +
              option("browser", "Browser voice" + (browserVoice ? "" : " — none found"),
                     current.voice_source) +
            "</select>" +
            '<span class="tiny muted">' + esc(voiceSummary()) + "</span></div>" +
          '<div class="field"><label for="user">Profile name</label>' +
            '<input id="user" value="' + esc(profile()) + '">' +
            '<span class="tiny muted">Separate profiles keep separate progress.</span></div>' +
          '<div class="btn-row"><button class="btn btn-primary" id="save">Save</button>' +
            '<button class="btn" id="testvoice">Test voice</button>' +
            '<span class="tiny muted" id="saved"></span></div>' +
        "</div>" +
        '<div class="card" style="margin-top:18px;border-color:var(--bad)">' +
          "<h2>Reset progress</h2>" +
          '<p class="tiny muted">Deletes every lesson score and review schedule for this profile.</p>' +
          '<button class="btn" id="reset">Reset everything</button>' +
        "</div>");

      document.getElementById("save").addEventListener("click", function () {
        localStorage.setItem("punjaber.user", document.getElementById("user").value.trim() || "local");
        api("/settings", {
          method: "PUT",
          body: {
            script: document.getElementById("script").value,
            gender: document.getElementById("gender").value,
            audio: document.getElementById("audio").value === "true",
            voice_source: document.getElementById("voice_source").value
          }
        }).then(function (saved) {
          settings = saved;
          document.getElementById("saved").textContent = "Saved.";
          refreshBadge();
        }).catch(showError);
      });

      // Speaking from a real click also sidesteps autoplay blocking, so this
      // is a reliable way to tell whether audio works at all.
      document.getElementById("testvoice").addEventListener("click", function () {
        var previous = settings.audio;
        settings.audio = true;
        settings.voice_source = document.getElementById("voice_source").value;
        speak("ਸਤ ਸ੍ਰੀ ਅਕਾਲ", false);
        settings.audio = previous;
        document.getElementById("saved").textContent =
          usingBrowserVoice() ? "Playing via browser voice…" : "Playing via built-in offline voice…";
      });

      document.getElementById("reset").addEventListener("click", function () {
        if (!confirm("Delete all progress for this profile?")) return;
        api("/reset", { method: "POST" }).then(function () { location.hash = "#/"; route(); });
      });
    });
  }

  // --- recording studio ---------------------------------------------------
  //
  // Records native-speaker audio for every phrase the course speaks. Clips are
  // keyed by the text, so recording a word once replaces the synthesiser for
  // that word everywhere it appears. The list is long, so the flow is built
  // around the keyboard: space to record and stop, and it walks you forward.

  var studio = {
    rows: [],
    filter: "todo",
    cursor: 0,
    recorder: null,
    chunks: [],
    stream: null,
    recording: false,
    lastBlob: null,
    lastText: null,
    error: ""
  };

  function recordingSupported() {
    return !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia && window.MediaRecorder);
  }

  function preferredMime() {
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return "";
    var candidates = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    for (var i = 0; i < candidates.length; i++) {
      if (MediaRecorder.isTypeSupported(candidates[i])) return candidates[i];
    }
    return "";
  }

  // The cursor is a position in the whole course, never in the filtered view.
  // Filtering the cursor as well was a trap: recording a phrase dropped it out
  // of the "to record" list, so Prev could never reach it to fix a bad take.
  function currentRow() {
    if (!studio.rows.length) return null;
    if (studio.cursor >= studio.rows.length) studio.cursor = studio.rows.length - 1;
    if (studio.cursor < 0) studio.cursor = 0;
    return studio.rows[studio.cursor];
  }

  function matchesFilter(row) {
    if (studio.filter === "todo") return !row.recorded;
    if (studio.filter === "done") return !!row.recorded;
    return true;
  }

  // Rows shown in the list below the booth. Purely a view: it never limits
  // where Prev and Next can take you.
  function listedRows() {
    return studio.rows
      .map(function (row, index) { return { row: row, index: index }; })
      .filter(function (entry) { return matchesFilter(entry.row); });
  }

  function nextUnrecordedFrom(start) {
    for (var i = start; i < studio.rows.length; i++) {
      if (!studio.rows[i].recorded) return i;
    }
    // Wrap, so a gap left earlier in the course still gets picked up.
    for (var j = 0; j < start && j < studio.rows.length; j++) {
      if (!studio.rows[j].recorded) return j;
    }
    return -1;
  }

  function viewStudio() {
    return api("/studio/texts").then(function (data) {
      studio.rows = data.texts;
      // Open where the work is, so returning to the studio resumes rather
      // than starting from the top of a course you have half-recorded.
      var resume = nextUnrecordedFrom(0);
      studio.cursor = resume === -1 ? 0 : resume;
      renderStudio();
    });
  }

  function renderStudio() {
    var total = studio.rows.length;
    var done = studio.rows.filter(function (r) { return r.recorded; }).length;
    var percent = total ? Math.round((done / total) * 100) : 0;
    var row = currentRow();

    if (!recordingSupported()) {
      render('<h1>Recording studio</h1>' +
        '<div class="card"><h2>Your browser cannot record here</h2>' +
        '<p class="tiny muted">Recording needs microphone access, which browsers only grant on a secure origin. ' +
        'Open the app at <strong>http://localhost:8000</strong> rather than by IP address, and use Chrome, Edge or Firefox.</p>' +
        '<p class="tiny muted">Everything else in Punjaber still works — you will just hear the built-in voice.</p></div>');
      return;
    }

    render('' +
      '<div class="hero">' +
        "<div><h1>Recording studio</h1>" +
        '<p class="sub">Record each phrase in your own voice. The whole app switches to your recording the moment it is saved.</p></div>' +
        '<div class="hero-stats">' +
          '<div><div class="stat-value">' + done + "/" + total + '</div><div class="stat-label">Recorded</div></div>' +
          '<div><div class="stat-value">' + percent + '%</div><div class="stat-label">Complete</div></div>' +
        "</div>" +
      "</div>" +
      '<div class="progressbar" style="margin-bottom:20px"><i style="width:' + percent + '%"></i></div>' +
      (studio.error ? '<div class="studio-error">' + esc(studio.error) + "</div>" : "") +
      studioBooth(row) +
      studioFilters(done, total) +
      studioList());

    wireSpeak(view);
    wireStudio();
  }

  function studioBooth(row) {
    if (!row) {
      return '<div class="card studio-booth"><div class="empty" style="padding:20px">' +
        "<h2>Nothing to record</h2></div></div>";
    }

    var remaining = studio.rows.filter(function (r) { return !r.recorded; }).length;

    return '' +
      '<div class="card studio-booth">' +
        '<div class="booth-meta">' +
          '<span class="unit-num">' +
            (row.unit_order === 0 ? "Primer" : "Unit " + row.unit_order) + "</span>" +
          '<span class="tiny muted">' + esc(row.lesson_title) + "</span>" +
          (row.recorded ? '<span class="chip-done">✓ recorded</span>' : "") +
          '<span class="tiny muted" style="margin-left:auto">' +
            (studio.cursor + 1) + " of " + studio.rows.length +
            (row.uses > 1 ? " · used " + row.uses + " times" : "") + "</span>" +
        "</div>" +
        '<div class="booth-text pa">' + esc(row.text) + "</div>" +
        '<div class="booth-roman">' + esc(row.roman) + "</div>" +
        '<div class="booth-en">' + esc(row.en) + "</div>" +
        '<div class="booth-controls">' +
          '<button class="btn" id="prev"' + (studio.cursor === 0 ? " disabled" : "") + '>← Prev</button>' +
          '<button class="btn ' + (studio.recording ? "btn-recording" : "btn-primary") + '" id="rec">' +
            (studio.recording ? "⏹ Stop (space)"
              : row.recorded ? "⏺ Re-record (space)" : "⏺ Record (space)") + "</button>" +
          '<button class="btn" id="next"' +
            (studio.cursor >= studio.rows.length - 1 ? " disabled" : "") + ">Next →</button>" +
        "</div>" +
        '<div class="booth-controls" style="margin-top:8px">' +
          '<button class="btn" id="play-mine"' + (row.recorded ? "" : " disabled") + '>▶ My take</button>' +
          '<button class="btn" id="play-synth">🔉 Synth</button>' +
          '<button class="btn" id="drop"' + (row.recorded ? "" : " disabled") + ">🗑 Delete</button>" +
          (remaining
            ? '<button class="btn btn-ghost" id="skip">Next to record (' + remaining + ") →</button>"
            : "") +
        "</div>" +
        '<div class="booth-status ' + (studio.recording ? "live" : "") + '">' +
          (studio.recording
            ? '<span class="rec-dot"></span> Recording — press space or click Stop when done'
            : row.recorded
              ? "✓ Recorded. Press space to record it again, or ▶ to check it."
              : "Not recorded yet. Press space to start.") +
        "</div>" +
        '<div class="tiny muted" style="margin-top:10px">' +
          "Keys: <kbd>space</kbd> record/stop · <kbd>←</kbd> <kbd>→</kbd> step through every phrase · " +
          "<kbd>n</kbd> next unrecorded · <kbd>p</kbd> play yours · <kbd>s</kbd> play synth" +
        "</div>" +
      "</div>";
  }

  function studioFilters(done, total) {
    function tab(value, label) {
      return '<button class="filter-tab' + (studio.filter === value ? " on" : "") +
        '" data-filter="' + value + '">' + label + "</button>";
    }
    return '<div class="filter-tabs">' +
      tab("todo", "To record (" + (total - done) + ")") +
      tab("done", "Recorded (" + done + ")") +
      tab("all", "All (" + total + ")") +
      "</div>";
  }

  function studioList() {
    var entries = listedRows();
    if (!entries.length) {
      return '<div class="empty" style="padding:24px">' +
        (studio.filter === "todo"
          ? "<h2>Every phrase is recorded 🎉</h2>" +
            '<p class="tiny muted">The course now speaks entirely in your voice. ' +
            "Use All to step back through and check any of them.</p>"
          : '<p class="tiny muted">Nothing matches this filter yet.</p>') +
        "</div>";
    }

    // Render a window around the cursor rather than all 323 rows, but anchor it
    // to where the cursor actually sits in the filtered view so the current
    // phrase stays on screen when it is listed at all.
    var position = 0;
    entries.forEach(function (entry, i) {
      if (entry.index <= studio.cursor) position = i;
    });
    var start = Math.max(0, position - 6);
    var slice = entries.slice(start, start + 40);
    var hidden = entries.length - slice.length;

    return '<div class="studio-list">' + slice.map(function (entry) {
      var row = entry.row;
      return '' +
        '<button class="studio-row' + (entry.index === studio.cursor ? " on" : "") +
          (row.recorded ? " done" : "") + '" data-jump="' + entry.index + '">' +
          '<span class="row-dot">' + (row.recorded ? "✓" : "•") + "</span>" +
          '<span class="row-body">' +
            '<span class="pa row-pa">' + esc(row.text) + "</span>" +
            '<span class="row-sub">' + esc(row.roman) + " — " + esc(row.en) + "</span>" +
          "</span>" +
          '<span class="tiny muted">' + esc(row.lesson_id) + "</span>" +
        "</button>";
    }).join("") +
      (hidden > 0
        ? '<div class="tiny muted" style="text-align:center;padding:8px">' +
          hidden + " more not shown — use the arrows or a filter to reach them</div>"
        : "") +
      "</div>";
  }

  // --- studio actions -----------------------------------------------------

  function studioSetCursor(index) {
    studio.cursor = index;
    studio.error = "";
    renderStudio();
  }

  function studioMove(delta) {
    if (studio.recording) return;
    var next = studio.cursor + delta;
    if (next < 0 || next >= studio.rows.length) return;
    studioSetCursor(next);
  }

  function studioSkipToTodo() {
    if (studio.recording) return;
    var next = nextUnrecordedFrom(studio.cursor + 1);
    if (next === -1) return;
    studioSetCursor(next);
  }

  function startRecording() {
    var row = currentRow();
    if (!row || studio.recording) return;

    studio.error = "";
    navigator.mediaDevices.getUserMedia({ audio: true }).then(function (stream) {
      studio.stream = stream;
      studio.chunks = [];
      var mime = preferredMime();
      studio.recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);

      studio.recorder.ondataavailable = function (event) {
        if (event.data && event.data.size) studio.chunks.push(event.data);
      };
      studio.recorder.onstop = function () {
        var blob = new Blob(studio.chunks, { type: studio.recorder.mimeType || "audio/webm" });
        stopStream();
        uploadTake(row, blob);
      };

      studio.recorder.start();
      studio.recording = true;
      renderStudio();
    }).catch(function (error) {
      studio.error = "Microphone unavailable: " + (error.message || error.name) +
        ". Check the browser's microphone permission for this site.";
      studio.recording = false;
      renderStudio();
    });
  }

  function stopRecording() {
    if (!studio.recording || !studio.recorder) return;
    studio.recording = false;
    // onstop fires asynchronously and does the uploading.
    studio.recorder.stop();
  }

  function stopStream() {
    if (studio.stream) {
      studio.stream.getTracks().forEach(function (track) { track.stop(); });
      studio.stream = null;
    }
  }

  function uploadTake(row, blob) {
    studio.lastBlob = blob;
    studio.lastText = row.text;
    var wasRecorded = !!row.recorded;

    var form = new FormData();
    form.append("text", row.text);
    form.append("clip", blob, "take" + (blob.type.indexOf("ogg") > -1 ? ".ogg" : ".webm"));

    fetch("/api/recordings", { method: "POST", body: form })
      .then(function (response) {
        if (!response.ok) {
          return response.json().catch(function () { return {}; }).then(function (payload) {
            throw new Error(payload.detail || "Upload failed (" + response.status + ")");
          });
        }
        return response.json();
      })
      .then(function () {
        row.recorded = true;
        recordedTexts[row.text] = true;
        // Move on automatically — with 300 phrases to get through, clicking
        // "next" every time is the difference between an afternoon and an
        // ordeal. Re-recording an earlier take is the exception: stay put so
        // you can play it back and check you actually fixed it.
        if (!wasRecorded) {
          var next = nextUnrecordedFrom(studio.cursor + 1);
          if (next !== -1) studio.cursor = next;
        }
        renderStudio();
      })
      .catch(function (error) {
        studio.error = error.message;
        renderStudio();
      });
  }

  function deleteTake() {
    var row = currentRow();
    if (!row || !row.recorded) return;
    api("/recordings?text=" + encodeURIComponent(row.text), { method: "DELETE" })
      .then(function () {
        row.recorded = false;
        delete recordedTexts[row.text];
        if (studio.lastText === row.text) { studio.lastBlob = null; studio.lastText = null; }
        renderStudio();
      })
      .catch(function (error) { studio.error = error.message; renderStudio(); });
  }

  function playMine() {
    var row = currentRow();
    if (!row) return;
    // Cache-bust so a re-recording is heard rather than the previous take.
    player.pause();
    player.playbackRate = 1;
    player.src = "/api/speech?text=" + encodeURIComponent(row.text) + "&t=" + Date.now();
    var started = player.play();
    if (started && started.catch) started.catch(function () {});
  }

  function playSynth() {
    var row = currentRow();
    if (!row) return;
    player.pause();
    player.playbackRate = 1;
    player.src = "/api/speech?synth=true&text=" + encodeURIComponent(row.text);
    var started = player.play();
    if (started && started.catch) started.catch(function () {});
  }

  function studioKeys(event) {
    // Only while the studio is on screen, and never while typing in a field.
    if (location.hash.indexOf("#/studio") !== 0) {
      document.removeEventListener("keydown", studioKeys);
      return;
    }
    if (/^(input|textarea|select)$/i.test((event.target.tagName || ""))) return;

    if (event.key === " ") {
      event.preventDefault();
      return studio.recording ? stopRecording() : startRecording();
    }
    if (event.key === "ArrowRight") { event.preventDefault(); return studioMove(1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); return studioMove(-1); }
    if (event.key === "n" || event.key === "N") return studioSkipToTodo();
    if (event.key === "p" || event.key === "P") return playMine();
    if (event.key === "s" || event.key === "S") return playSynth();
  }

  function wireStudio() {
    var rec = document.getElementById("rec");
    if (rec) {
      rec.addEventListener("click", function () {
        return studio.recording ? stopRecording() : startRecording();
      });
    }
    var bind = function (id, handler) {
      var node = document.getElementById(id);
      if (node) node.addEventListener("click", handler);
    };
    bind("play-mine", playMine);
    bind("play-synth", playSynth);
    bind("next", function () { studioMove(1); });
    bind("prev", function () { studioMove(-1); });
    bind("skip", studioSkipToTodo);
    bind("drop", deleteTake);

    on("[data-filter]", "click", function (event) {
      studio.filter = event.currentTarget.getAttribute("data-filter");
      studio.error = "";
      // Bring the booth to the first row this filter shows, but leave the
      // cursor alone if it already points at one — switching to "Recorded"
      // to check the take you are standing on should not move you away.
      var entries = listedRows();
      if (entries.length && !matchesFilter(studio.rows[studio.cursor])) {
        studio.cursor = entries[0].index;
      }
      renderStudio();
    });
    on("[data-jump]", "click", function (event) {
      studioSetCursor(Number(event.currentTarget.getAttribute("data-jump")));
    });

    document.removeEventListener("keydown", studioKeys);
    document.addEventListener("keydown", studioKeys);
  }

  // --- routing ------------------------------------------------------------

  function showError(error) {
    render('<div class="empty"><h1>Something went wrong</h1><p class="muted">' +
           esc(error.message) + '</p><a class="btn" href="#/">Back to the course</a></div>');
  }

  function refreshBadge() {
    api("/course").then(function (data) {
      dueBadge.hidden = !data.summary.due_count;
      dueBadge.textContent = data.summary.due_count;
    }).catch(function () {});
  }

  function markNav(name) {
    document.querySelectorAll("[data-nav]").forEach(function (link) {
      link.classList.toggle("active", link.getAttribute("data-nav") === name);
      // Hide the studio entirely where recording is switched off, rather than
      // offering a tab that can only fail.
      if (link.getAttribute("data-nav") === "studio") link.hidden = !studioEnabled;
    });
  }

  function route() {
    var hash = location.hash || "#/";
    var parts = hash.replace(/^#\/?/, "").split("/");

    if (parts[0] === "lesson" && parts[1]) {
      markNav("home");
      return viewLesson(parts[1]).catch(showError);
    }
    if (parts[0] === "review") {
      markNav("review");
      return viewReview().catch(showError);
    }
    if (parts[0] === "studio") {
      markNav("studio");
      if (!studioEnabled) {
        render('<div class="empty"><h1>Recording is off here</h1>' +
          "<p>This deployment serves the course read-only. Record new audio by " +
          "running Punjaber locally with <code>make start</code>, then redeploy.</p>" +
          '<a class="btn btn-primary" href="#/">Back to the course</a></div>');
        return Promise.resolve();
      }
      return viewStudio().catch(showError);
    }
    if (parts[0] === "progress") {
      markNav("progress");
      return viewProgress().catch(showError);
    }
    if (parts[0] === "settings") {
      markNav("settings");
      return viewSettings().catch(showError);
    }
    markNav("home");
    return viewHome().catch(showError);
  }

  window.addEventListener("hashchange", route);

  // Load preferences and audio capability first, so the very first render and
  // the first spoken word both honour them.
  Promise.all([
    api("/settings").then(function (loaded) { settings = loaded; }).catch(function () {}),
    api("/health").then(function (h) {
      offlineAudio = !!(h.audio && h.audio.offline);
      studioEnabled = h.studio !== false;
    })
      .catch(function () { offlineAudio = false; }),
    loadRecordingManifest()
  ]).then(route);
})();
