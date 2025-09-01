import mongoose, { Document, Schema } from "mongoose";
import bcrypt from "bcryptjs";

export interface IUser extends Document {
  email: string;
  password?: string;
  googleId?: string;
  name: string;
  dateOfBirth?: Date;
  isVerified: boolean;
  otp?: string;
  otpExpiry?: Date;
  comparePassword(password: string): Promise<boolean>;
}

const UserSchema = new Schema<IUser>(
  {
    email: {
      type: String,
      required: true,
      unique: true,
      lowercase: true,
      trim: true,
    },
    password: {
      type: String,
      required: function () {
        return !this.googleId;
      },
    },
    googleId: String,
    name: {
      type: String,
      required: true,
    },
    dateOfBirth: Date,
    isVerified: {
      type: Boolean,
      default: false,
    },
    otp: String,
    otpExpiry: Date,
  },
  {
    timestamps: true,
  },
);

UserSchema.pre("save", async function (next) {
  if (!this.isModified("password") || !this.password) return next();
  this.password = await bcrypt.hash(this.password, 10);
  next();
});

UserSchema.methods.comparePassword = async function (password: string) {
  if (!this.password) return false;
  return bcrypt.compare(password, this.password);
};

export default mongoose.model<IUser>("User", UserSchema);
