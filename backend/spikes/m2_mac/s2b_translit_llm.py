"""S2b: Roman -> Devanagari name transliteration without fairseq.

Usage: s2b_translit_llm.py <model_id|baseline> [device]
Self-written test set (no names from samples/). "exact" = equals the primary form;
"ok" = equals the primary or an accepted same-pronunciation variant.
"""

import resource
import sys
import time

# (roman, primary, accepted variants)
NAMES: list[tuple[str, str, list[str]]] = [
    ("Krishan Lal", "कृष्ण लाल", ["किशन लाल", "कृष्ण लाल"]),
    ("Krishna Kumar", "कृष्णा कुमार", ["कृष्ण कुमार"]),
    ("Amit Dighal", "अमित डिघल", ["अमित दिघल"]),
    ("Sunil Sharma", "सुनील शर्मा", ["सुनिल शर्मा"]),
    ("Rajesh Singh", "राजेश सिंह", ["राजेश सिंघ"]),
    ("Priya Gupta", "प्रिया गुप्ता", []),
    ("Anita Devi", "अनीता देवी", ["अनिता देवी"]),
    ("Vikram Choudhary", "विक्रम चौधरी", ["विक्रम चौधुरी"]),
    ("Manoj Tiwari", "मनोज तिवारी", ["मनोज तिवारी"]),
    ("Sandeep Kaur", "संदीप कौर", ["सन्दीप कौर"]),
    ("Gurmeet Singh", "गुरमीत सिंह", ["गुरमीत सिंघ"]),
    ("Pooja Verma", "पूजा वर्मा", ["पुजा वर्मा"]),
    ("Deepak Yadav", "दीपक यादव", ["दिपक यादव"]),
    ("Sushil Kumar", "सुशील कुमार", ["सुशिल कुमार"]),
    ("Ramesh Chand", "रमेश चंद", ["रमेश चन्द", "रमेश चांद"]),
    ("Neha Agarwal", "नेहा अग्रवाल", ["नेहा अगरवाल"]),
    ("Harish Saini", "हरीश सैनी", ["हरिश सैनी"]),
    ("Jaspreet Kaur", "जसप्रीत कौर", ["जसप्रित कौर"]),
    ("Mohit Malik", "मोहित मलिक", []),
    ("Kavita Rani", "कविता रानी", []),
    ("Naresh Bansal", "नरेश बंसल", ["नरेश बन्सल"]),
    ("Arvind Kejriwal", "अरविंद केजरीवाल", ["अरविन्द केजरीवाल"]),
    ("Shyam Lal", "श्याम लाल", []),
    ("Sanjay Dutt", "संजय दत्त", ["सन्जय दत्त"]),
    ("Rakesh Jain", "राकेश जैन", []),
    ("Suman Lata", "सुमन लता", []),
    ("Bhupinder Hooda", "भूपिंदर हुड्डा", ["भूपेंद्र हुड्डा", "भूपिन्दर हुड्डा"]),
    ("Ashok Tanwar", "अशोक तंवर", ["अशोक तँवर", "अशोक तनवर"]),
    ("Dinesh Rathi", "दिनेश राठी", ["दिनेश राठी"]),
    ("Meena Kumari", "मीना कुमारी", ["मिना कुमारी"]),
    ("Yogesh Chaudhary", "योगेश चौधरी", []),
    ("Tarun Bhatia", "तरुण भाटिया", ["तरूण भाटिया"]),
    ("Satbir Dahiya", "सतबीर दहिया", ["सत्बीर दहिया"]),
    ("Poonam Rana", "पूनम राणा", ["पुनम राणा", "पूनम राना"]),
    ("Vinod Chhikara", "विनोद छिकारा", []),
    ("Anil Kumar", "अनिल कुमार", []),
    ("Surender Kadian", "सुरेंदर कादियान", ["सुरेन्दर कादियान", "सुरेंद्र कादियान"]),
    ("Raj Kumari", "राज कुमारी", []),
    ("Mukesh Ahlawat", "मुकेश अहलावत", []),
    ("Babita Phogat", "बबीता फोगाट", ["बबिता फोगाट"]),
]

PROMPT = (
    "Transliterate Indian names written in English letters into Hindi (Devanagari). "
    "Output only the Devanagari name, nothing else. Keep the pronunciation as spoken in Hindi.\n"
    "Examples:\nSuresh Patel -> सुरेश पटेल\nGeeta Rani -> गीता रानी\n"
    "Harpreet Singh -> हरप्रीत सिंह\nVishal Chauhan -> विशाल चौहान\nKishan Lal -> किशन लाल\n"
)


def load_llm(model_id: str, device: str):  # noqa: ANN201
    """Load a causal LM in bf16 on the device."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(model_id)
    model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.bfloat16).to(device).eval()

    def fn(name: str) -> str:
        msgs = [{"role": "system", "content": PROMPT}, {"role": "user", "content": f"{name} ->"}]
        ids = tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt",
                                      return_dict=True).to(device)
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=40, do_sample=False)
        text = tok.decode(out[0, ids["input_ids"].shape[-1]:], skip_special_tokens=True)
        return text.strip().splitlines()[0].replace("->", "").strip() if text.strip() else ""

    return fn


def load_baseline():  # noqa: ANN201
    """Rule-based ITRANS/HK-style scheme transliteration (indic-transliteration)."""
    from indic_transliteration import sanscript

    def fn(name: str) -> str:
        return sanscript.transliterate(name.lower(), sanscript.ITRANS, sanscript.DEVANAGARI)

    return fn


def main() -> None:
    """Run the test set and print accuracy, speed and memory."""
    model_id = sys.argv[1]
    device = sys.argv[2] if len(sys.argv) > 2 else "mps"
    t = time.time()
    fn = load_baseline() if model_id == "baseline" else load_llm(model_id, device)
    load_s = time.time() - t
    fn("Amit Sharma")  # warm-up
    exact = ok = 0
    times = []
    for roman, primary, alts in NAMES:
        t = time.time()
        got = fn(roman)
        times.append(time.time() - t)
        hit_exact = got == primary
        hit_ok = hit_exact or got in alts
        exact += hit_exact
        ok += hit_ok
        if not hit_ok:
            print(f"MISS {roman!r}: got {got!r} expected {primary!r}")
    n = len(NAMES)
    print(f"RESULT {model_id} device={device} n={n} exact={exact / n:.0%} ok={ok / n:.0%} "
          f"load_s={load_s:.1f} s_per_name={sum(times) / n:.2f} "
          f"peak_rss_GB={resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**30:.1f}")


if __name__ == "__main__":
    main()
