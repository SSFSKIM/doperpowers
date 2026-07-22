// quiz.js — reusable retrieval-practice widget.
// Usage: <div class="quiz" id="quiz"></div>
//        <script> renderQuiz(document.getElementById('quiz'), QUESTIONS); </script>
// QUESTIONS: [{stem, options: [..], answer: idx, expl}]
// Options are shuffled at render so position carries no signal.
function renderQuiz(root, questions) {
  let answered = 0, correct = 0;
  const scoreEl = document.createElement("p");
  scoreEl.className = "score";
  questions.forEach((q, qi) => {
    const box = document.createElement("div");
    box.className = "q";
    const stem = document.createElement("p");
    stem.className = "stem";
    stem.textContent = (qi + 1) + ". " + q.stem;
    box.appendChild(stem);
    const order = q.options.map((_, i) => i).sort(() => Math.random() - 0.5);
    order.forEach((oi) => {
      const b = document.createElement("button");
      b.className = "opt";
      b.textContent = q.options[oi];
      b.onclick = () => {
        if (box.classList.contains("answered")) return;
        box.classList.add("answered");
        answered++;
        if (oi === q.answer) { b.classList.add("correct"); correct++; }
        else {
          b.classList.add("wrong");
          [...box.querySelectorAll("button.opt")].forEach((bb) => {
            if (bb.textContent === q.options[q.answer]) bb.classList.add("correct");
          });
        }
        expl.style.display = "block";
        if (answered === questions.length)
          scoreEl.textContent = "결과: " + correct + " / " + questions.length +
            (correct === questions.length ? " — 완벽." : " — 틀린 문항의 해설을 소리 내어 다시 설명해볼 것.");
      };
      box.appendChild(b);
    });
    const expl = document.createElement("p");
    expl.className = "expl";
    expl.textContent = q.expl;
    box.appendChild(expl);
    root.appendChild(box);
  });
  root.appendChild(scoreEl);
}
