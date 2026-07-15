"""PowerGrader AI workflow — handles packet creation, safety gate, and OpenRouter scoring.

This module does not call Canvas APIs.
"""

import json

import feedback_pipeline as fp
import feedback_safety as safety
import openrouter_client as orc
from webui import config, source_materials, workspace
from powergrader import ai_workflow_support, context, copilot_packet, packet, privacy


def run_ai_workflow(
    *,
    mode: str,
    submitted: list[dict],
    assignment_name: str,
    assignment_description: str,
    course_id: str,
    course_name: str = "",
    assignment_id: str,
    session_id: str,
    rubric_name: str,
    persona_id: str,
    selected_model: str,
    response_kind: str,
    source_text: str,
    source_files_json: str,
    source_uploads,
    has_openrouter_key: bool,
    source_context_override: dict | None = None,
    artifact_assignment_name: str | None = None,
    feedback_pattern_id: str = "",
    copilot_batch_prefix: str | None = None,
) -> dict:
    """Run the AI/packet workflow for a PowerGrader session.

    Returns a dict with keys: ok, error, status_code, privacy_steps,
    privacy_artifacts, ai_by_uid, packet_zip, budget, debug_path.
    """
    privacy_steps: list[dict] = []
    privacy_artifacts: dict = {}
    ai_by_uid: dict = {}
    ai_item_by_uid: dict = {}
    ai_failures: dict = {}
    budget_result = None
    debug_path = None
    copilot_info = None
    source_context: dict = {}
    artifact_name = artifact_assignment_name or assignment_name

    if mode not in {"packet", "assisted"}:
        privacy_steps.append(privacy.privacy_step(
            "fast_mode", "Grade Myself selected", "warn",
            "Grade Myself selected. No AI packet or API call was requested.",
        ))
        return ai_workflow_support.workflow_result(
            ok=True,
            privacy_steps=privacy_steps,
            privacy_artifacts=privacy_artifacts,
            ai_by_uid=ai_by_uid,
            ai_failures=ai_failures,
            source_context=source_context,
        )

    if mode == "assisted" and not has_openrouter_key:
        privacy_steps.append(privacy.privacy_step(
            "llm_send", "Sent Safe AI Packet to selected LLM", "warn",
            "No OpenRouter key is saved, so PowerGrader stayed local and did not send anything.",
        ))
        return ai_workflow_support.workflow_result(
            ok=True,
            privacy_steps=privacy_steps,
            privacy_artifacts=privacy_artifacts,
            ai_by_uid=ai_by_uid,
            ai_failures=ai_failures,
            source_context=source_context,
        )

    # ---- Build source context ----
    workspace.ensure_workspace()
    try:
        if source_context_override is not None:
            source_context = source_context_override
        else:
            source_context = context.build_source_context(
                source_text, source_files_json, source_uploads, strict=True
            )
    except Exception as e:
        return ai_workflow_support.workflow_result(
            ok=False,
            error=f"Could not read selected source material: {e}",
            privacy_steps=privacy_steps,
            privacy_artifacts=privacy_artifacts,
            ai_by_uid=ai_by_uid,
            source_context=source_context,
        )

    source_warning_text = "; ".join(source_materials.context_warnings(source_context))
    ai_workflow_support.append_source_context_step(
        privacy_steps,
        privacy.privacy_step,
        source_context,
        source_warning_text,
    )

    vault = context.vault()
    bundle = fp.pseudonymize_submissions(submitted, vault, artifact_name)
    bundle = context.apply_shared_context(bundle, assignment_description, source_context)

    if not bundle["students"]:
        # No students passed pseudonymization; fall through to session building
        pass
    else:
        vault.save()
        privacy_steps.append(privacy.privacy_step(
            "pseudonymize", "Assigned pseudonyms and separated identities", "ok",
            f"{len(bundle['students'])} pseudonymized student bundle(s); real names remain in the local vault.",
        ))

        verdict = safety.scan_payload(bundle, vault)
        if not verdict["green"]:
            privacy_steps.append(privacy.privacy_step(
                "safety_scan", "Checked pseudonymized payload for real names", "warn",
                (
                    "Potential real-name text was found before the deeper packet scrub. "
                    "The packet writer will scrub again and exclude any unsafe student from the LLM payload."
                ),
            ))
        else:
            privacy_steps.append(privacy.privacy_step(
                "safety_scan", "Checked pseudonymized payload for real names", "ok",
                "No hard PII matches found before the file-writing step.",
            ))

        rubric_text = context.load_rubric_text(rubric_name)
        persona = config.get_persona(persona_id)
        patterns = config.list_feedback_patterns()
        fb_pattern = next((item for item in patterns if item.get("id") == feedback_pattern_id), None)
        fb_pattern = fb_pattern or (patterns[0] if patterns else None)
        model = selected_model

        safe_dir, private_dir = privacy.feedback_artifact_dirs(
            course_name=course_name or course_id,
            course_id=course_id,
            assignment_name=artifact_name,
            assignment_id=assignment_id,
            mode=mode,
        )
        if not safe_dir or not private_dir:
            privacy_steps.append(privacy.privacy_step(
                "safe_private", "Wrote Safe AI Packet and Private decoder artifacts", "failed",
                "Workspace folders were unavailable. Nothing was sent to the LLM.",
            ))
            return ai_workflow_support.workflow_result(
                ok=False,
                error="Could not resolve Safe AI Packet / Private decoder folders — finish workspace setup first.",
                privacy_steps=privacy_steps,
                privacy_artifacts=privacy_artifacts,
                ai_by_uid=ai_by_uid,
                source_context=source_context,
            )

        write_result = fp.write_safe_and_private(
            bundle,
            vault,
            safe_dir,
            private_dir,
            ai_ta_name=persona.get("name") or "your teaching assistant",
            persona=persona,
            protected=config.active_protected_names(),
            submissions=submitted,
            rubric_text=rubric_text,
        )

        if not write_result.get("safe_bundle"):
            privacy_steps.append(privacy.privacy_step(
                "safe_private", "Wrote Safe AI Packet and Private decoder artifacts", "failed",
                "The deeper scrub found hard violations. Nothing was sent to the LLM.",
                log=write_result.get("log", []),
            ))
            return ai_workflow_support.workflow_result(
                ok=False,
                error="Safe AI Packet write failed — privacy gate blocked this batch.",
                privacy_steps=privacy_steps,
                privacy_artifacts=privacy_artifacts,
                ai_by_uid=ai_by_uid,
                source_context=source_context,
            )

        privacy_artifacts = ai_workflow_support.build_privacy_artifacts(write_result, safe_dir, private_dir)

        privacy_steps.append(privacy.privacy_step(
            "safe_private", "Wrote inspectable Safe AI Packet and Private decoder files", "ok",
            (
                f"Fake-name bundle, {privacy_artifacts['student_txt_count']} readable text file(s), "
                "private raw bundle, and who-is-who decoder saved."
            ),
            safe_folder=safe_dir,
            private_folder=private_dir,
        ))

        manual_count = privacy_artifacts["attachment_only_count"] + privacy_artifacts["excluded_count"]
        if manual_count:
            privacy_steps.append(privacy.privacy_step(
                "manual_review", "Flagged work that needs teacher/manual handling", "warn",
                (
                    f"{manual_count} item(s) were kept local for manual review "
                    "instead of being sent to the LLM."
                ),
            ))

        if privacy_artifacts.get("shared_context_excluded"):
            privacy_steps.append(privacy.privacy_step(
                "source_context_safe", "Checked shared source context after scrubbing", "warn",
                (
                    "The shared source context was kept out of the Safe AI Packet because a real "
                    "roster identifier survived scrubbing."
                ),
            ))

        try:
            with open(write_result["safe_bundle"], encoding="utf-8") as f:
                llm_bundle = json.load(f)
        except Exception as e:
            privacy_steps.append(privacy.privacy_step(
                "safe_payload", "Loaded Safe AI Packet for LLM scoring", "failed",
                f"Could not reload the Safe AI Packet: {e}. Nothing was sent.",
            ))
            return ai_workflow_support.workflow_result(
                ok=False,
                error=f"Could not load Safe AI Packet: {e}",
                privacy_steps=privacy_steps,
                privacy_artifacts=privacy_artifacts,
                ai_by_uid=ai_by_uid,
                source_context=source_context,
            )

        safe_students = len(llm_bundle.get("students") or [])
        packet_info = packet.build_safe_ai_packet(artifact_name, safe_dir, write_result, llm_bundle, persona)
        privacy_artifacts.update(packet_info)
        privacy_steps.append(privacy.privacy_step(
            "safe_ai_packet", "Created Safe AI Packet", "ok",
            (
                "Packet ZIP includes fake-name student responses, source material, "
                "rubric instructions, and the paste-back JSON format."
            ),
            path=packet_info.get("packet_zip"),
        ))

        if mode == "packet" and safe_students > 0:
            copilot_info = copilot_packet.build_copilot_batches(
                assignment_name=artifact_name,
                safe_dir=safe_dir,
                llm_bundle=llm_bundle,
                rubric_text=rubric_text,
                persona=persona,
                batch_id_prefix=copilot_batch_prefix,
                safe_bundle_path=write_result.get("safe_bundle"),
            )
            privacy_artifacts["copilot_packet_folder"] = copilot_info.get("packet_folder")
            privacy_artifacts["copilot_readme"] = copilot_info.get("readme_path")
            privacy_artifacts["copilot_batch_count"] = copilot_info.get("batch_count", 0)
            privacy_artifacts["copilot_student_count"] = copilot_info.get("student_count", 0)
            copilot_warnings = copilot_info.get("warnings") or []
            copilot_detail = (
                f"{copilot_info['batch_count']} batch folder(s), each with 3 numbered upload files."
            )
            if copilot_warnings:
                copilot_detail += f" {copilot_warnings[0]}"
            privacy_steps.append(privacy.privacy_step(
                "copilot_batches",
                "Created Copilot batch folders",
                "warn" if copilot_warnings else "ok",
                copilot_detail,
                path=copilot_info.get("packet_folder"),
                action_label="Open Copilot batch folder",
            ))

        if safe_students == 0:
            privacy_steps.append(privacy.privacy_step(
                "llm_send", "Prepared Safe AI Packet for scoring", "warn",
                "No students passed the packet writer for automated scoring. Grade this batch by hand.",
            ))
            privacy_steps.append(privacy.privacy_step(
                "reidentify", "Reattached real names locally", "warn",
                "No AI results were generated, so there was nothing to reattach.",
            ))
        elif mode == "packet":
            privacy_steps.append(privacy.privacy_step(
                "manual_ai_chat", "Ready for your AI chat", "ok",
                "Canvas Expert stopped before any API send. Use the Safe AI Packet with your own AI chat, then paste JSON results back here.",
            ))
        else:
            # assisted mode with OpenRouter key
            privacy_steps.append(privacy.privacy_step(
                "safe_payload", "Loaded Safe AI Packet for LLM scoring", "ok",
                f"{safe_students} fake-name student response(s) selected for OpenRouter.",
            ))

            budget_result = orc.teacher_workflow_budget(
                llm_bundle,
                rubric_text,
                model,
                student_count=safe_students,
                persona=persona,
                feedback_pattern=fb_pattern,
                output_tokens_per_student=source_materials.response_preset(response_kind)["output_tokens_per_student"],
            )

            if not budget_result["ok"]:
                estimate = budget_result.get("estimated_cost")
                estimate_text = f" Estimated batch cost: ${estimate:.2f}." if estimate is not None else ""
                privacy_steps.append(privacy.privacy_step(
                    "price_check", "Verified model price before sending", "failed",
                    "; ".join(budget_result.get("reasons") or ["cost could not be verified"]) + estimate_text,
                ))
                return ai_workflow_support.workflow_result(
                    ok=False,
                    error=(
                        f"OpenRouter model '{model}' cannot be used for teacher auto-scoring. "
                        + "; ".join(budget_result.get("reasons") or ["cost could not be verified"])
                        + estimate_text
                    ),
                    privacy_steps=privacy_steps,
                    privacy_artifacts=privacy_artifacts,
                    ai_by_uid=ai_by_uid,
                    budget=budget_result,
                    copilot_packet=copilot_info,
                    source_context=source_context,
                )

            estimate = budget_result.get("estimated_cost")
            warning = "; ".join(budget_result.get("warnings") or [])
            privacy_steps.append(privacy.privacy_step(
                "price_check", "Verified model price before sending", "warn" if warning else "ok",
                (
                    f"Model {model}; estimated batch cost "
                    + (f"${estimate:.2f}" if estimate is not None else "available after provider billing")
                    + (f". {warning}" if warning else ".")
                    + " Estimate assumes fresh input; provider prompt caching is not guaranteed."
                ),
            ))

            try:
                all_students = list(llm_bundle.get("students") or [])
                media_students = [
                    student for student in all_students
                    if any(response.get("media") for response in student.get("responses") or [])
                ]
                media_pseudonyms = {str(student.get("pseudonym") or "") for student in media_students}
                text_students = [
                    student for student in all_students
                    if str(student.get("pseudonym") or "") not in media_pseudonyms
                ]
                results = []
                isolated_failures: list[tuple[str, Exception]] = []
                if text_students:
                    text_bundle = {**llm_bundle, "students": text_students}
                    try:
                        results.extend(orc.score(
                            text_bundle, rubric_text, persona,
                            api_key=config.get_openrouter_key(), model=model,
                            feedback_pattern=fb_pattern,
                            model_metadata=budget_result.get("model_metadata"),
                        ))
                    except Exception as exc:
                        if not media_students:
                            raise
                        for student in text_students:
                            isolated_failures.append((str(student.get("pseudonym") or ""), exc))
                # Keep each media-bearing request isolated so an image or
                # provider failure cannot associate evidence with another
                # pseudonym or discard the rest of the class.
                for student in media_students:
                    one_student_bundle = {**llm_bundle, "students": [student]}
                    try:
                        results.extend(orc.score(
                            one_student_bundle, rubric_text, persona,
                            api_key=config.get_openrouter_key(), model=model,
                            feedback_pattern=fb_pattern,
                            model_metadata=budget_result.get("model_metadata"),
                        ))
                    except Exception as exc:
                        isolated_failures.append((str(student.get("pseudonym") or ""), exc))

                for pseudonym, _exc in isolated_failures:
                    who = vault.reverse(pseudonym)
                    if who and who.get("canvas_id"):
                        ai_failures[str(who["canvas_id"])] = ai_workflow_support.AI_MANUAL_REVIEW_MESSAGE

                if not results and isolated_failures:
                    raise isolated_failures[-1][1]

                requested = len(all_students)
                successful = len({str(row.get("pseudonym") or "") for row in results if row.get("pseudonym")})
                failed = len({pseudo for pseudo, _ in isolated_failures if pseudo})
                privacy_steps.append(privacy.privacy_step(
                    "llm_send", "Sent only the Safe AI Packet to OpenRouter", "ok",
                    f"Requested {requested} pseudonymized student(s); {successful} returned AI drafts and {failed} need manual review. Real names were not included.",
                ))
                rows = fp.reidentify(results, vault)
                unresolved = sum(1 for row in rows if not row.get("resolved"))
                privacy_steps.append(privacy.privacy_step(
                    "reidentify", "Reattached real names locally", "warn" if unresolved else "ok",
                    (
                        f"{len(rows)} AI result(s) joined back to local Canvas IDs."
                        + (f" {unresolved} unresolved result(s) need review." if unresolved else "")
                    ),
                ))
                ai_by_uid = fp.merge_rows_by_uid(rows)
                ai_item_by_uid = fp.item_rows_by_uid(rows)
                if ai_failures:
                    privacy_steps.append(privacy.privacy_step(
                        "ai_manual_review", "Marked isolated AI failures for teacher review", "warn",
                        f"{len(ai_failures)} student(s) received no AI draft; manual grading is required.",
                    ))
            except Exception as e:
                debug_path = privacy.write_openrouter_debug_file(
                    private_dir,
                    artifact_name,
                    session_id=session_id,
                    course_id=course_id,
                    assignment_id=assignment_id,
                    model_id=model,
                    safe_students=safe_students,
                    packet_info=packet_info,
                    budget=budget_result,
                    privacy_steps=privacy_steps,
                    exc=e,
                )
                privacy_steps.append(privacy.privacy_step(
                    "llm_send", "Sent only the Safe AI Packet to OpenRouter", "failed",
                    f"OpenRouter error: {e}",
                    path=debug_path,
                    action_label="Open OpenRouter debug file",
                ))
                return ai_workflow_support.workflow_result(
                    ok=False,
                    error=f"OpenRouter error: {e}",
                    privacy_steps=privacy_steps,
                    privacy_artifacts=privacy_artifacts,
                    ai_by_uid=ai_by_uid,
                    ai_item_by_uid=ai_item_by_uid,
                    ai_failures=ai_failures,
                    budget=budget_result,
                    debug_path=debug_path,
                    copilot_packet=copilot_info,
                    source_context=source_context,
                )

    return ai_workflow_support.workflow_result(
        ok=True,
        privacy_steps=privacy_steps,
        privacy_artifacts=privacy_artifacts,
        ai_by_uid=ai_by_uid,
        ai_item_by_uid=ai_item_by_uid,
        ai_failures=ai_failures,
        packet_zip=privacy_artifacts.get("packet_zip"),
        budget=budget_result,
        debug_path=debug_path,
        copilot_packet=copilot_info,
        source_context=source_context,
    )
