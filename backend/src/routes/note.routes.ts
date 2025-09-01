import { Router } from "express";
import { body } from "express-validator";
import * as noteController from "../controllers/note.controller";
import { authenticate } from "../middleware/auth.middleware";

const router = Router();

router.use(authenticate);

router.get("/", noteController.getNotes);
router.post(
  "/",
  [body("title").trim().notEmpty(), body("content").trim().notEmpty()],
  noteController.createNote,
);
router.delete("/:id", noteController.deleteNote);

export default router;
