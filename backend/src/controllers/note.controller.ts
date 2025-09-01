import type { Response } from "express";
import Note from "../models/Note.model";
import type { AuthRequest } from "../middleware/auth.middleware";

export const getNotes = async (req: AuthRequest, res: Response) => {
  try {
    const notes = await Note.find({ userId: req.userId }).sort({
      createdAt: -1,
    });
    res.json(notes);
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch notes" });
  }
};

export const createNote = async (req: AuthRequest, res: Response) => {
  try {
    const { title, content } = req.body;

    const note = new Note({
      userId: req.userId,
      title,
      content,
    });

    await note.save();
    res.status(201).json(note);
  } catch (error) {
    res.status(500).json({ error: "Failed to create note" });
  }
};

export const deleteNote = async (req: AuthRequest, res: Response) => {
  try {
    const { id } = req.params;

    const note = await Note.findOneAndDelete({
      _id: id,
      userId: req.userId,
    });

    if (!note) {
      return res.status(404).json({ error: "Note not found" });
    }

    res.json({ message: "Note deleted successfully" });
  } catch (error) {
    res.status(500).json({ error: "Failed to delete note" });
  }
};
